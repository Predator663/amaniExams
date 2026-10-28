#!/usr/bin/env python3
"""Load test for the Amani exam API (NFR-03, NFR-05; acceptance test: "a full-school simultaneous login and
exam start works without errors").

It needs only Python 3.9+ (no extra packages), so it runs on a laptop or in Termux. It pretends to be many students:
each one logs in, opens her exams, starts the exam, answers every question (pausing like a real student), and finishes.

    1. On a TEST server:   python manage.py seed_loadtest --students 500 --questions 40 --yes
       (the test server must run with LOGIN_THROTTLE_RATE=100000/min, because every simulated student has the same IP)
    2. From any computer:  python loadtest/run_load.py --base-url https://TEST-SERVER --students 500

It prints response times (median, 95th and 99th percentile, slowest) and checks them against the SRS:
  - an answer is saved in about 1 second          (NFR-03)  -> answer p95 must be under 1000 ms
  - every student gets in and starts without error (9.2)    -> zero failed requests
Exit status 0 = passed, 1 = failed. Use --report to save the numbers as JSON."""
import argparse
import json
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.times = {}   # label -> [milliseconds]
        self.errors = {}  # label -> {status: count}
        self.students_done = 0
        self.students_failed = 0

    def add(self, label, ms, status):
        with self.lock:
            self.times.setdefault(label, []).append(ms)
            if not 200 <= status < 300:
                self.errors.setdefault(label, {})
                self.errors[label][status] = self.errors[label].get(status, 0) + 1


def call(stats, label, method, url, token=None, body=None, timeout=60):
    """One HTTP request. Returns (status, json_or_None). Never raises: a network failure is status 0."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Token " + token)
    started = time.perf_counter()
    status, payload = 0, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception:  # connection refused, timeout, DNS ...
        raw = b""
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        payload = None
    stats.add(label, (time.perf_counter() - started) * 1000, status)
    return status, payload


def pick_response(question):
    """A valid answer for the question shapes this API serves to students."""
    kind, content = question["type"], question.get("content", {})
    if kind == "mcq_single":
        return random.choice(content["options"])["id"]
    if kind == "mcq_multi":
        return [content["options"][0]["id"]]
    if kind == "true_false":
        return random.choice([True, False])
    if kind == "matching":
        return {l["id"]: r["id"] for l, r in zip(content["left"], content["right"])}
    if kind == "ordering":
        return [i["id"] for i in content["items"]]
    return "4"


def simulate(i, args, stats):
    base, name = args.base_url.rstrip("/"), f"{args.prefix}{i:04d}"
    time.sleep(args.ramp * (i - 1) / max(1, args.students))  # spread the logins over the ramp-up time
    code, d = call(stats, "login", "POST", base + "/api/auth/login/", body={"username": name, "password": args.password})
    if code != 200 or not d:
        return False
    token = d["token"]
    call(stats, "presence", "POST", base + "/api/presence/", token)
    code, exams = call(stats, "exam list", "GET", base + "/api/student/exams/", token)
    if code != 200 or not exams:
        return False
    exam = next((e for e in exams if e["state"] in ("open", "in_progress") and (not args.exam_id or e["id"] == args.exam_id)), None)
    if not exam:
        return False
    code, state = call(stats, "start exam", "POST", f"{base}/api/student/exams/{exam['id']}/start/", token, {"agree_rules": True})
    if code not in (200, 201) or not state:
        return False
    aid = state["attempt_id"]
    while not state.get("finished"):
        time.sleep(random.uniform(args.think_min, args.think_max))  # reading and thinking
        code, state = call(stats, "save answer", "POST", f"{base}/api/attempts/{aid}/answer/", token,
                           {"question_id": state["question"]["id"], "response": pick_response(state["question"])})
        if code != 200 or not state:
            return False
        if random.random() < 0.05:  # now and then a phone refreshes the page and resumes (EDAY-06)
            code, state = call(stats, "resume", "GET", f"{base}/api/attempts/{aid}/", token)
            if code != 200 or not state:
                return False
    if args.check_results:
        call(stats, "result (before publish: 404 expected)", "GET", f"{base}/api/results/{aid}/", token)
    return True


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="for example https://exam-test.onrender.com")
    ap.add_argument("--students", type=int, default=500)
    ap.add_argument("--prefix", default="lt")
    ap.add_argument("--password", default="LoadTest-2026")
    ap.add_argument("--exam-id", type=int, default=0, help="only if several exams are open")
    ap.add_argument("--concurrency", type=int, default=0, help="students at the same time (0 = all of them)")
    ap.add_argument("--ramp", type=float, default=10, help="seconds over which the logins are spread (0 = all at once)")
    ap.add_argument("--think-min", type=float, default=0.5)
    ap.add_argument("--think-max", type=float, default=3.0)
    ap.add_argument("--answer-p95-ms", type=float, default=1000)
    ap.add_argument("--login-p95-ms", type=float, default=3000)
    ap.add_argument("--check-results", action="store_true")
    ap.add_argument("--report", help="write the numbers to this JSON file")
    args = ap.parse_args()
    if not args.base_url.startswith(("http://", "https://")):
        ap.error("--base-url must start with http:// or https://")

    stats, gate = Stats(), threading.Semaphore(args.concurrency or args.students)
    began = time.time()

    def worker(i):
        with gate:
            ok = False
            try:
                ok = simulate(i, args, stats)
            finally:
                with stats.lock:
                    if ok:
                        stats.students_done += 1
                    else:
                        stats.students_failed += 1

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(1, args.students + 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - began

    print(f"\n{args.students} students, {elapsed:.0f} s. Finished the exam: {stats.students_done}. Failed: {stats.students_failed}.\n")
    print(f"{'request':44s} {'count':>6s} {'median':>8s} {'p95':>8s} {'p99':>8s} {'slowest':>8s}  (milliseconds)")
    report = {"students": args.students, "finished": stats.students_done, "failed": stats.students_failed, "seconds": round(elapsed), "requests": {}}
    for label, vals in sorted(stats.times.items()):
        row = {"count": len(vals), "median": statistics.median(vals), "p95": percentile(vals, 95), "p99": percentile(vals, 99), "max": max(vals)}
        report["requests"][label] = {k: round(v) for k, v in row.items()}
        print(f"{label:44s} {row['count']:6d} {row['median']:8.0f} {row['p95']:8.0f} {row['p99']:8.0f} {row['max']:8.0f}")
    bad = {k: v for k, v in stats.errors.items() if not k.startswith("result (before")}
    if bad:
        print("\nErrors (status 0 = no answer / timeout):")
        for label, codes in bad.items():
            print(f"  {label}: {codes}")

    problems = []
    if stats.students_failed:
        problems.append(f"{stats.students_failed} student(s) could not finish the exam")
    if bad:
        problems.append("some requests failed")
    ans = stats.times.get("save answer")
    if ans and percentile(ans, 95) > args.answer_p95_ms:
        problems.append(f"saving an answer is too slow (p95 {percentile(ans, 95):.0f} ms, limit {args.answer_p95_ms:.0f})")
    login = stats.times.get("login")
    if login and percentile(login, 95) > args.login_p95_ms:
        problems.append(f"login is too slow (p95 {percentile(login, 95):.0f} ms, limit {args.login_p95_ms:.0f})")
    report["passed"] = not problems
    report["problems"] = problems
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
    print("\nRESULT: " + ("PASSED" if not problems else "FAILED - " + "; ".join(problems)))
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
