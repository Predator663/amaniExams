"""Tips shown on the 'exam submitted' screen (EDAY-09): rotating, subject-specific and motivational.

`finish_tips(subject_name, lang, seed)` is deterministic for a given seed (use the attempt id), so a
page refresh shows the same tips, while different students and different exams see different ones.
Swahili wording should be checked by a Kiswahili teacher before go-live."""
import random

EXAM_TIPS = {
    "en": [
        "Read every question twice before you answer. Small words like 'not' and 'except' change everything.",
        "Spend your time wisely: if a question is taking too long, make your best choice and move on.",
        "Drink some water and rest your eyes after a long exam. A tired brain remembers less.",
        "After an exam, do not worry about the answers you cannot change. Look forward to learning from your results.",
        "Plan your revision in short sessions of 25 minutes with a 5-minute break. It works better than one long night.",
        "Sleep well the night before an exam. Sleep helps your brain store what you studied.",
        "When your results come, start with the topics marked 'revise'. Those are your quickest wins.",
        "Practise a little every day. Ten questions a day beats one hundred questions the night before.",
    ],
    "sw": [
        "Soma kila swali mara mbili kabla ya kujibu. Maneno madogo kama 'si' na 'isipokuwa' hubadilisha maana yote.",
        "Tumia muda wako vizuri: swali likichukua muda mrefu, chagua jibu lako bora kisha endelea.",
        "Kunywa maji na pumzisha macho yako baada ya mtihani mrefu. Akili iliyochoka hukumbuka kidogo.",
        "Baada ya mtihani, usihangaike na majibu usiyoweza kubadilisha. Tazamia kujifunza kutokana na matokeo yako.",
        "Panga marudio yako kwa vipindi vifupi vya dakika 25 na mapumziko ya dakika 5. Ni bora kuliko usiku mmoja mrefu.",
        "Lala vizuri usiku kabla ya mtihani. Usingizi husaidia ubongo kuhifadhi ulichosoma.",
        "Matokeo yako yakitoka, anza na mada zilizoandikwa 'rudia'. Hizo ndizo ushindi wako wa haraka.",
        "Fanya mazoezi kidogo kila siku. Maswali kumi kila siku ni bora kuliko maswali mia moja usiku kabla ya mtihani.",
    ],
}

MOTIVATION = {
    "en": [
        "You showed up and finished. That is already a win. Be proud of yourself!",
        "Every exam teaches you something. Your next one will be even better.",
        "Mistakes are how brains grow. Use your review to turn them into strengths.",
        "Small steps every day take you far. Keep going, you are doing well!",
        "You do not need to be perfect, only a little better than last time.",
        "Believe in yourself. Hard work and patience always pay off.",
    ],
    "sw": [
        "Ulikuja na ukamaliza. Hiyo tayari ni ushindi. Jivunie!",
        "Kila mtihani hukufundisha kitu. Mtihani wako ujao utakuwa bora zaidi.",
        "Makosa ndiyo yanayokuza ubongo. Tumia mapitio yako kuyageuza kuwa nguvu.",
        "Hatua ndogo kila siku zinakupeleka mbali. Endelea, unafanya vizuri!",
        "Huhitaji kuwa mkamilifu, bali kuwa bora kidogo kuliko mara iliyopita.",
        "Jiamini. Bidii na subira hulipa daima.",
    ],
}

# keyword in the (lowercased) subject name -> tips for that subject
SUBJECT_TIPS = {
    ("math", "hisabati"): {
        "en": ["In Mathematics, write each step of your working. Most mistakes hide in the steps you skip.",
               "Check your answer by putting it back into the question. It takes ten seconds and saves marks.",
               "Learn your multiplication tables and formulae well. Speed in the basics frees time for hard problems."],
        "sw": ["Katika Hisabati, andika kila hatua ya kazi yako. Makosa mengi yamejificha kwenye hatua unazoruka.",
               "Hakiki jibu lako kwa kulirudisha kwenye swali. Inachukua sekunde kumi na inaokoa alama.",
               "Jifunze vizuri jedwali la kuzidisha na fomula. Kasi kwenye misingi hukupa muda kwa maswali magumu."],
    },
    ("english",): {
        "en": ["In English, read widely. Every new word you meet in a book is a free lesson.",
               "For grammar questions, say the sentence aloud in your head. Your ear often catches what your eye misses.",
               "Build your vocabulary by learning five new words each week and using them in your own sentences."],
        "sw": ["Katika Kiingereza, soma sana. Kila neno jipya unalokutana nalo kitabuni ni somo la bure.",
               "Kwa maswali ya sarufi, sema sentensi kimoyomoyo. Sikio mara nyingi hugundua kile jicho linachokosa.",
               "Jenga msamiati wako kwa kujifunza maneno matano mapya kila wiki na kuyatumia kwenye sentensi zako."],
    },
    ("kiswahili", "swahili"): {
        "en": ["In Kiswahili, practise reading aloud. Good fluency makes comprehension questions much easier.",
               "Learn the noun classes and their agreements. They are the key to correct sentences.",
               "Read proverbs (methali) and sayings (misemo) often. They appear in exams and teach wisdom."],
        "sw": ["Katika Kiswahili, jizoeze kusoma kwa sauti. Ufasaha mzuri hurahisisha maswali ya ufahamu.",
               "Jifunze ngeli za nomino na viambishi vyake. Ndizo ufunguo wa sentensi sahihi.",
               "Soma methali na misemo mara kwa mara. Hutokea mitihanini na hufundisha hekima."],
    },
    ("biolog", "baiolojia"): {
        "en": ["In Biology, draw and label diagrams often. A clear diagram can earn marks and helps you remember.",
               "Link structure to function: ask 'why is it built this way?' for every organ and cell.",
               "Learn scientific terms by their parts (for example 'hydro' means water). It makes long words easy."],
        "sw": ["Katika Biolojia, chora na weka majina kwenye michoro mara kwa mara. Mchoro safi hukupa alama na hukusaidia kukumbuka.",
               "Unganisha muundo na kazi: uliza 'kwa nini imeundwa hivi?' kwa kila kiungo na seli.",
               "Jifunze istilahi za kisayansi kwa sehemu zake. Hurahisisha maneno marefu."],
    },
    ("chem", "kemia"): {
        "en": ["In Chemistry, balance your equations and check the state symbols. Examiners look for both.",
               "Learn the periodic table in groups, not one by one. Patterns are easier to remember than lists.",
               "Practise naming compounds and writing formulae a little every day."],
        "sw": ["Katika Kemia, sawazisha milinganyo yako na uhakiki alama za hali. Wasahihishaji hutafuta vyote viwili.",
               "Jifunze jedwali la vipindi kwa makundi, si moja moja. Mifumo ni rahisi kukumbuka kuliko orodha.",
               "Jizoeze kutaja misombo na kuandika fomula kidogo kila siku."],
    },
    ("phys", "fizikia"): {
        "en": ["In Physics, write the formula, then substitute the numbers, then give the answer with its unit.",
               "Draw a quick sketch of the situation before you calculate. It prevents silly mistakes.",
               "Check that your units match before you calculate (for example centimetres and metres)."],
        "sw": ["Katika Fizikia, andika fomula, kisha weka namba, kisha toa jibu pamoja na kipimo chake.",
               "Chora mchoro mfupi wa hali kabla ya kuhesabu. Huzuia makosa ya kizembe.",
               "Hakikisha vipimo vinalingana kabla ya kuhesabu (kwa mfano sentimita na mita)."],
    },
    ("geog", "jiografia"): {
        "en": ["In Geography, practise reading maps: scale, direction and key first.",
               "Learn examples of places for each topic. Real examples make answers stronger.",
               "Link causes and effects: for each feature, ask what caused it and what it causes."],
        "sw": ["Katika Jiografia, jizoeze kusoma ramani: anza na kipimo, mwelekeo na ufunguo.",
               "Jifunze mifano ya sehemu halisi kwa kila mada. Mifano halisi huimarisha majibu.",
               "Unganisha sababu na athari: kwa kila hali, uliza nini kilisababisha na inasababisha nini."],
    },
    ("hist", "historia"): {
        "en": ["In History, build a timeline. Knowing what came before and after makes events easy to remember.",
               "For every event, remember the causes, the main people and the results.",
               "Practise explaining events in your own words instead of only memorising dates."],
        "sw": ["Katika Historia, tengeneza mstari wa matukio. Kujua nini kilitangulia na nini kilifuata hurahisisha kukumbuka.",
               "Kwa kila tukio, kumbuka sababu, watu wakuu na matokeo.",
               "Jizoeze kueleza matukio kwa maneno yako badala ya kukariri tarehe tu."],
    },
    ("civic", "uraia"): {
        "en": ["In Civics, connect each idea to real life in your community. Examples make answers stronger.",
               "Learn the key words of each topic and their meanings. They are often the whole question."],
        "sw": ["Katika Uraia, unganisha kila wazo na maisha halisi katika jamii yako. Mifano huimarisha majibu.",
               "Jifunze maneno muhimu ya kila mada na maana zake. Mara nyingi ndiyo swali lenyewe."],
    },
}


def finish_tips(subject_name, lang="en", seed=0):
    """Up to three tips: one for the subject (or a study tip if the subject is unknown), one exam tip and
    one motivational message. Each is {"kind": "subject" | "exam" | "motivation", "text": ...}."""
    lang = lang if lang in ("en", "sw") else "en"
    rnd = random.Random(f"tips:{seed}")
    name = (subject_name or "").lower()
    subject_pool = []
    for keys, tips in SUBJECT_TIPS.items():
        if any(k in name for k in keys):
            subject_pool = tips[lang]
            break
    out = []
    if subject_pool:
        out.append({"kind": "subject", "text": rnd.choice(subject_pool)})
    exam_pool = EXAM_TIPS[lang]
    first = rnd.choice(exam_pool)
    out.append({"kind": "exam", "text": first})
    out.append({"kind": "motivation", "text": rnd.choice(MOTIVATION[lang])})
    return out
