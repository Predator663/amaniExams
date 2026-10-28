"use client";
import Shell from "@/components/Shell";
import StaffNav from "@/components/StaffNav";
import LiveBoard from "@/components/LiveBoard";

/** Live monitor + history: live exams, then finished ones with who completed, who submitted partly,
    and who did not sit (with parent phone numbers, administrators only). */
export default function Monitor() {
  return (
    <Shell bare title="Live monitor">
      <StaffNav />
      <LiveBoard />
    </Shell>
  );
}
