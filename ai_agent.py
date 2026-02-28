import requests
import json
import time
import os
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ─────────────────────────────────────────────
# YOUR FULL PROFILE
# ─────────────────────────────────────────────
MY_PROFILE = {
    "name":             "Parmeshwar Gurlewad",
    "first_name":       "Parmeshwar",
    "last_name":        "Gurlewad",
    "email":            "parmeshwarg08@gmail.com",
    "phone":            "7666845301",
    "location":         "Hyderabad",
    "gender":           "Male",
    "current_company":  "Pranakshit IT Solution",
    "current_role":     "Software Engineer",
    "experience_years": "1",
    "skills":           "Java, Spring Boot, Spring Framework, Hibernate, Microservices, REST APIs, MySQL, PostgreSQL, React, JavaScript, Git, Maven",
    "resume_path":      r"C:\Users\parme\Desktop\Param_SoftwareEngineer.pdf",
    "expected_ctc":     "400000",
    "current_ctc":      "0",
    "notice_period":    "0",
    "degree":           "Bachelor of Computer Science",
    "college":          "MGM College of Computer Science",
    "passing_year":     "2024",
    "percentage":       "75",
    "summary": """Java Full Stack Developer, 1+ year experience at Pranakshit IT Solution, Hyderabad.
Skills: Java, Spring Boot, Microservices, REST APIs, Hibernate, MySQL, PostgreSQL, React, Git, CI/CD.
Education: B.Sc Computer Science, MGM College, 2024. Expected CTC: 4 LPA. Notice: Immediate joiner."""
}

OLLAMA_URL    = "http://localhost:11434/api/generate"
MODEL         = "mistral"
AGENT_PROFILE = os.path.expanduser("~") + r"\AI_Agent_Chrome_Profile"
EXCEL_DIR     = os.path.expanduser("~") + r"\Desktop"

# ─────────────────────────────────────────────
# SAFE NAVIGATION
# ─────────────────────────────────────────────
def safe_goto(page, url, timeout=40000):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        time.sleep(2)
        return True
    except PlaywrightTimeout:
        time.sleep(2)
        return True
    except Exception as e:
        print(f"   ❌ Nav error: {e}")
        return False

# ─────────────────────────────────────────────
# FILL INPUT SAFELY
# ─────────────────────────────────────────────
def fill_field(page, selectors, value):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(); time.sleep(0.2)
                el.triple_click()
                el.fill(str(value))
                return True
        except:
            continue
    return False

# ─────────────────────────────────────────────
# AI ANSWER FOR ANY QUESTION
# ─────────────────────────────────────────────
def ai_answer_question(question_text, options=None):
    options_str = f"\nOptions available: {', '.join(options)}" if options else ""
    prompt = f"""You are filling a job application for this candidate:
{MY_PROFILE['summary']}

Question: "{question_text}"{options_str}

Reply with ONLY the answer. No explanation. No punctuation.
Rules:
- Projects → Yes (has worked on microservices, REST API projects)
- Work experience → Yes
- Authorized to work in India → Yes  
- Willing to relocate → Yes
- Immediate joiner / notice period → Yes / 0 / Immediate
- Years of experience → 1
- Current CTC → 0
- Expected CTC → 400000
- Skills → Java, Spring Boot, REST APIs, MySQL
- Gender → Male
- Degree → Bachelor of Computer Science
- Fresher or Experienced → Experienced

Answer:"""
    try:
        r = requests.post(OLLAMA_URL, json={"model":MODEL,"prompt":prompt,"stream":False}, timeout=15)
        answer = r.json()["response"].strip().split("\n")[0].strip().strip('"').strip("'")
        return answer
    except:
        return "Yes"  # safe default

# ─────────────────────────────────────────────
# CHECK EXTERNAL APPLY
# ─────────────────────────────────────────────
def is_external_apply(page):
    try:
        body = page.inner_text("body").lower()[:5000]
        if any(t in body for t in ["apply on company site","apply on employer site","apply at company"]):
            return True
    except:
        pass
    for sel in ['a:has-text("Apply on company site")', 'button:has-text("Apply on company site")']:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except:
            pass
    return False

# ─────────────────────────────────────────────
# CHECK SUCCESS
# ─────────────────────────────────────────────
def check_success(page):
    try:
        body = page.inner_text("body").lower()[:5000]
        return any(t in body for t in [
            "applied successfully","application submitted",
            "you have already applied","application has been sent",
            "successfully applied","thank you for applying",
            "your application has been"
        ])
    except:
        return False

# ─────────────────────────────────────────────
# HANDLE NAUKRI CHATBOT MODAL
# This is the key fix - handles the popup with
# questions like "Did you work on any project?"
# ─────────────────────────────────────────────
def handle_chatbot_modal(page):
    """Handles Naukri's chatbot-style question modal step by step."""
    print("      💬 Handling chatbot questions...")
    max_questions = 15

    for q_num in range(max_questions):
        time.sleep(1.5)

        # Check if modal is closed / success
        if check_success(page):
            print("      ✅ Application submitted via chatbot!")
            return True

        # Find the modal container
        modal = None
        for sel in [
            '.chatbot-container',
            '[class*="chatbot"]',
            '[class*="questionnaire"]',
            '.apply-questionnaire',
            '[data-test*="chatbot"]',
            '.naukri-chatbot',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    modal = el
                    break
            except:
                pass

        # Get current question text
        question_text = ""
        for sel in [
            '.chatbot-message',
            '[class*="question"]',
            '.ssrc__question',
            'p.question',
            '[class*="chatbot"] p',
            '[class*="questionnaire"] label',
            '.modal p',
            'div[class*="question"] p',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    txt = el.inner_text().strip()
                    if txt and len(txt) > 3:
                        question_text = txt
                        break
            except:
                pass

        if question_text:
            print(f"      ❓ Question: {question_text[:60]}")

        # ── Handle radio buttons in modal ──────────────────
        radio_handled = False
        try:
            # Find all radio options currently visible
            radios = page.query_selector_all('input[type="radio"]')
            visible_radios = [(r, r) for r in radios if r.is_visible()]

            if visible_radios:
                # Get labels for each radio
                option_map = []  # (label_text, radio_element)
                for radio in radios:
                    if not radio.is_visible():
                        continue
                    try:
                        rid = radio.get_attribute("id") or ""
                        val = radio.get_attribute("value") or ""

                        # Try to get label text
                        label_text = ""
                        if rid:
                            lbl = page.query_selector(f'label[for="{rid}"]')
                            if lbl:
                                label_text = lbl.inner_text().strip()
                        if not label_text:
                            label_text = val

                        if label_text:
                            option_map.append((label_text.lower(), radio, label_text))
                    except:
                        continue

                if option_map:
                    options_list = [o[2] for o in option_map]
                    print(f"      🔘 Options: {options_list}")

                    # Ask AI which option to pick
                    ai_ans = ai_answer_question(
                        question_text or "Select the best option",
                        options_list
                    ).lower().strip()

                    print(f"      🤖 AI chose: '{ai_ans}'")

                    # Find best matching radio
                    clicked = False

                    # First try exact / contains match
                    for opt_lower, radio_el, opt_original in option_map:
                        if ai_ans in opt_lower or opt_lower in ai_ans:
                            try:
                                radio_el.click()
                                print(f"      ✅ Selected: '{opt_original}'")
                                clicked = True
                                radio_handled = True
                                time.sleep(0.5)
                                break
                            except:
                                pass

                    # If no match, pick "yes" or "skip this question" or first option
                    if not clicked:
                        for opt_lower, radio_el, opt_original in option_map:
                            if "yes" in opt_lower:
                                try:
                                    radio_el.click()
                                    print(f"      ✅ Defaulted to: '{opt_original}'")
                                    clicked = True
                                    radio_handled = True
                                    break
                                except:
                                    pass

                    if not clicked:
                        # Pick first option
                        try:
                            option_map[0][1].click()
                            print(f"      ✅ Picked first option: '{option_map[0][2]}'")
                            radio_handled = True
                        except:
                            pass

                    time.sleep(0.5)
        except Exception as e:
            pass

        # ── Handle text inputs in modal ────────────────────
        try:
            inputs = page.query_selector_all('input[type="text"], input[type="number"], input[type="tel"]')
            for inp in inputs:
                if not inp.is_visible():
                    continue
                current = inp.input_value() or ""
                if current.strip():
                    continue  # already filled
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                label_text  = question_text or placeholder

                answer = ai_answer_question(label_text)
                if answer:
                    inp.triple_click()
                    inp.fill(answer)
                    print(f"      🤖 Filled: '{label_text[:40]}' → '{answer}'")
                    time.sleep(0.3)
        except:
            pass

        # ── Handle textarea ────────────────────────────────
        try:
            tas = page.query_selector_all("textarea")
            for ta in tas:
                if ta.is_visible():
                    current = ta.input_value() or ""
                    if not current.strip():
                        ta.fill(f"Yes, I have worked on multiple Java projects including microservices and REST APIs using Spring Boot.")
                        time.sleep(0.3)
        except:
            pass

        # ── Handle select dropdowns ────────────────────────
        try:
            selects = page.query_selector_all("select")
            for sel_el in selects:
                if not sel_el.is_visible():
                    continue
                answer = ai_answer_question(question_text or "Select option")
                try:
                    sel_el.select_option(label=answer)
                except:
                    try:
                        sel_el.select_option(index=1)
                    except:
                        pass
        except:
            pass

        # ── Click Save / Next / Submit ─────────────────────
        time.sleep(0.5)
        btn_clicked = False

        for btn_text in ["Save", "Next", "Submit", "Continue", "Proceed", "Done"]:
            for sel in [
                f'button:has-text("{btn_text}")',
                f'[class*="save"]:has-text("{btn_text}")',
                f'[class*="btn"]:has-text("{btn_text}")',
            ]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        print(f"      ▶ Clicked '{btn_text}'")
                        btn_clicked = True
                        time.sleep(1.5)
                        break
                except:
                    pass
            if btn_clicked:
                break

        # Check success after clicking
        if check_success(page):
            print("      ✅ Applied successfully!")
            return True

        # If nothing happened, check if modal closed
        if not btn_clicked and not radio_handled:
            # Try pressing Enter as last resort
            try:
                page.keyboard.press("Enter")
                time.sleep(1)
            except:
                pass
            break

    return check_success(page)

# ─────────────────────────────────────────────
# HANDLE FULL APPLY FLOW
# ─────────────────────────────────────────────
def handle_apply_flow(page):
    max_steps = 15

    for step in range(max_steps):
        time.sleep(1.5)

        if check_success(page):
            return True

        # Check if chatbot modal is open
        chatbot_open = False
        for sel in [
            '.chatbot-container', '[class*="chatbot"]',
            '[class*="questionnaire"]', '.apply-questionnaire',
            '[class*="recruiter-question"]',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    chatbot_open = True
                    break
            except:
                pass

        # Also check if there are visible radio buttons (chatbot indicator)
        try:
            radios = page.query_selector_all('input[type="radio"]')
            if any(r.is_visible() for r in radios):
                chatbot_open = True
        except:
            pass

        if chatbot_open:
            result = handle_chatbot_modal(page)
            if result:
                return True
            break

        # Standard form filling
        fill_field(page, ['input[placeholder*="First name"]', 'input[id*="firstName"]'], MY_PROFILE["first_name"])
        fill_field(page, ['input[placeholder*="Last name"]',  'input[id*="lastName"]'],  MY_PROFILE["last_name"])
        fill_field(page, ['input[type="email"]'],                                          MY_PROFILE["email"])
        fill_field(page, ['input[type="tel"]', 'input[placeholder*="phone"]'],             MY_PROFILE["phone"])
        fill_field(page, ['input[placeholder*="current ctc"]', 'input[id*="currentCTC"]'], MY_PROFILE["current_ctc"])
        fill_field(page, ['input[placeholder*="expected"]',    'input[id*="expectedCTC"]'],MY_PROFILE["expected_ctc"])
        fill_field(page, ['input[placeholder*="notice"]',      'input[id*="notice"]'],     MY_PROFILE["notice_period"])
        fill_field(page, ['input[placeholder*="experience"]',  'input[id*="experience"]'], MY_PROFILE["experience_years"])

        # Upload resume
        try:
            for fi in page.query_selector_all('input[type="file"]'):
                try:
                    fi.set_input_files(MY_PROFILE["resume_path"])
                    time.sleep(1); break
                except:
                    pass
        except:
            pass

        # Click Submit / Apply
        submitted = False
        for sel in [
            'button:has-text("Apply Now")',
            'button:has-text("Apply")',
            'button:has-text("Submit")',
            'button[type="submit"]',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(); time.sleep(2)
                    submitted = True
                    break
            except:
                pass

        if check_success(page):
            return True

        if not submitted:
            break

    return check_success(page)

# ─────────────────────────────────────────────
# SCRAPE NAUKRI JOBS
# ─────────────────────────────────────────────
def scrape_naukri_jobs(page):
    jobs = []
    print("   🕷️  Scraping jobs...")
    for _ in range(4):
        page.mouse.wheel(0, 800); time.sleep(0.7)
    try:
        page.wait_for_selector(".srp-jobtuple-wrapper, .jobTuple", timeout=10000)
    except:
        pass

    cards = []
    for sel in [".srp-jobtuple-wrapper", ".jobTuple", "article.jobTuple"]:
        c = page.query_selector_all(sel)
        if c: cards = c; break

    print(f"   📦 Found {len(cards)} jobs")

    for card in cards:
        try:
            t  = card.query_selector("a.title, .title a, h2 a")
            co = card.query_selector("a.comp-name, .comp-name")
            ex = card.query_selector(".expwdth, .exp-wrap li")
            sa = card.query_selector(".sal-wrap li, .salary")
            lo = card.query_selector(".loc-wrap li, .location")
            po = card.query_selector(".job-post-day, .postDays, span.type-time")

            title = t.inner_text().strip() if t else "N/A"
            link  = ""
            if t:
                href = t.get_attribute("href") or ""
                link = href if href.startswith("http") else "https://www.naukri.com" + href

            if title != "N/A":
                jobs.append({
                    "title":    title,
                    "company":  co.inner_text().strip() if co else "N/A",
                    "exp":      ex.inner_text().strip() if ex else "N/A",
                    "salary":   sa.inner_text().strip() if sa else "Not disclosed",
                    "location": lo.inner_text().strip() if lo else "N/A",
                    "posted":   po.inner_text().strip() if po else "N/A",
                    "link":     link,
                    "applied":  "Pending"
                })
        except:
            continue

    print(f"   ✅ Scraped {len(jobs)} jobs!")
    return jobs

# ─────────────────────────────────────────────
# AUTO APPLY
# ─────────────────────────────────────────────
def naukri_auto_apply(page, job_title, location="", max_apply=5):
    print(f"\n🤖 NAUKRI AUTO APPLY: '{job_title}'")
    print(f"   ⏰ Last 24 hours only | 🎯 Max: {max_apply}\n")

    # Check login
    safe_goto(page, "https://www.naukri.com/mnjuser/homepage", timeout=30000)
    time.sleep(2)
    if "login" in page.url or "mnjuser" not in page.url:
        print("⚠️  Please login to Naukri then press ENTER...")
        input()

    keyword = job_title.lower().replace(" ", "-")
    url = (f"https://www.naukri.com/{keyword}-jobs"
           + (f"-in-{location.lower().replace(' ','-')}" if location and location.lower() != "any" else "")
           + f"?experienceMin=0&experienceMax=2&freshness=1")

    print(f"   🔗 {url}")
    safe_goto(page, url, timeout=40000)
    time.sleep(2)

    jobs = scrape_naukri_jobs(page)
    if not jobs:
        print("   ❌ No jobs found.")
        return []

    applied_count = 0; skipped_ext = 0; skipped_err = 0
    applied_jobs  = []
    search_url    = page.url

    for i, job in enumerate(jobs):
        if applied_count >= max_apply:
            print(f"\n✅ Reached limit of {max_apply}!")
            break
        if not job.get("link"):
            continue

        print(f"\n   [{applied_count+1}/{max_apply}] {job['title']} @ {job['company']}")
        print(f"   💰 {job['salary']} | 📍 {job['location']} | ⏰ {job['posted']}")

        safe_goto(page, job["link"], timeout=30000)
        time.sleep(2)

        # Skip external
        if is_external_apply(page):
            print("      🚫 External site — SKIPPING")
            job["applied"] = "Skipped (External)"
            skipped_ext += 1
            safe_goto(page, search_url, timeout=30000)
            time.sleep(1); continue

        # Find Apply button
        apply_btn = None
        for sel in [
            'button[id="apply-button"]',
            'button:has-text("Apply")',
            '#apply-button',
            '.apply-button',
            '.btn-apply',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    txt = (btn.inner_text() or "").lower()
                    if "company site" not in txt and "employer site" not in txt:
                        apply_btn = btn; break
            except:
                pass

        if not apply_btn:
            print("      ⏭️  No Apply button — skipping")
            job["applied"] = "Skipped (No button)"
            skipped_err += 1
            safe_goto(page, search_url, timeout=30000)
            time.sleep(1); continue

        apply_btn.click()
        time.sleep(2)

        if is_external_apply(page):
            print("      🚫 Redirected to external — SKIPPING")
            job["applied"] = "Skipped (External)"
            skipped_ext += 1
            try: page.go_back()
            except: pass
            safe_goto(page, search_url, timeout=30000)
            time.sleep(1); continue

        print("      📝 Filling application form...")
        success = handle_apply_flow(page)

        if success:
            applied_count += 1
            job["applied"] = "Applied ✅"
            applied_jobs.append({**job, "time": datetime.now().strftime("%d %b %Y %H:%M")})
            print(f"      🎉 APPLIED! Total: {applied_count}")
        else:
            job["applied"] = "Skipped (Form error)"
            skipped_err += 1
            print("      ⚠️  Could not complete — skipping")
            try: page.keyboard.press("Escape")
            except: pass

        safe_goto(page, search_url, timeout=30000)
        time.sleep(1.5)

    print(f"\n{'='*55}")
    print(f"  🏆 DONE! Applied: {applied_count} | External skipped: {skipped_ext} | Errors: {skipped_err}")
    print(f"{'='*55}")
    save_excel(jobs, job_title, applied_count)
    return applied_jobs

# ─────────────────────────────────────────────
# SEARCH ONLY
# ─────────────────────────────────────────────
def naukri_search_only(page, job_title, location=""):
    print(f"\n🔍 Naukri Search: '{job_title}' (last 24h)")
    safe_goto(page, "https://www.naukri.com/mnjuser/homepage", timeout=30000)
    keyword = job_title.lower().replace(" ", "-")
    url = (f"https://www.naukri.com/{keyword}-jobs"
           + (f"-in-{location.lower()}" if location and location.lower() != "any" else "")
           + "?freshness=1")
    safe_goto(page, url, timeout=40000)
    time.sleep(2)
    jobs = scrape_naukri_jobs(page)
    if jobs:
        ans = input(f"\n💾 Save {len(jobs)} jobs to Excel? (yes/no): ").strip().lower()
        if ans in ["yes","y",""]:
            save_excel(jobs, job_title)
    else:
        print("   ❌ No jobs found.")

# ─────────────────────────────────────────────
# SAVE EXCEL
# ─────────────────────────────────────────────
def save_excel(jobs, job_title, applied_count=0):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath  = os.path.join(EXCEL_DIR, f"Naukri_{job_title.replace(' ','_')}_{timestamp}.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Naukri Jobs"
    DARK="1F3864"; LIGHT="D9E1F2"; WHITE="FFFFFF"; GREEN="C6EFCE"; RED="FFC7CE"; YELLOW="FFEB9C"
    thin=Side(style="thin",color="CCCCCC"); bdr=Border(left=thin,right=thin,top=thin,bottom=thin)

    ws.merge_cells("A1:I1"); c=ws["A1"]
    c.value=f"Naukri Jobs (24h) · {job_title.title()} · {datetime.now().strftime('%d %b %Y')} · Applied: {applied_count}"
    c.font=Font(name="Arial",bold=True,size=13,color="FFD700")
    c.fill=PatternFill("solid",fgColor=DARK); c.alignment=Alignment(horizontal="center",vertical="center")
    ws.row_dimensions[1].height=28

    for ci,h in enumerate(["#","Job Title","Company","Exp","Salary","Location","Posted","Link","Status"],1):
        c=ws.cell(2,ci,h); c.font=Font(name="Arial",bold=True,size=11,color="FFFFFF")
        c.fill=PatternFill("solid",fgColor=DARK); c.alignment=Alignment(horizontal="center"); c.border=bdr
    ws.row_dimensions[2].height=22

    for i,job in enumerate(jobs,1):
        r=i+2; status=job.get("applied","Pending")
        fc = GREEN if "Applied" in status else YELLOW if "External" in status else RED if "error" in status.lower() or "Skipped" in status else (LIGHT if i%2==0 else WHITE)
        row=[i,job["title"],job["company"],job.get("exp","N/A"),job["salary"],job["location"],job["posted"],job["link"],status]
        for ci,val in enumerate(row,1):
            c=ws.cell(r,ci,val); c.font=Font(name="Arial",size=10)
            c.fill=PatternFill("solid",fgColor=fc); c.border=bdr
            c.alignment=Alignment(vertical="center",horizontal="center" if ci in(1,4,7,9) else "left",wrap_text=True)
            if ci==8 and isinstance(val,str) and val.startswith("http"):
                c.hyperlink=val; c.value="🔗 View"; c.font=Font(name="Arial",size=10,color="1155CC",underline="single")
        ws.row_dimensions[r].height=20

    for ci,w in enumerate([4,35,22,12,18,16,12,10,18],1):
        ws.column_dimensions[get_column_letter(ci)].width=w
    ws.freeze_panes="A3"; ws.auto_filter.ref=f"A2:I{len(jobs)+2}"
    wb.save(filepath); print(f"\n💾 Saved → {filepath}")

# ─────────────────────────────────────────────
# ASK AI
# ─────────────────────────────────────────────
def ask_ai(command):
    print(f"\n🤖 AI thinking...")
    prompt = f"""Return ONLY JSON. No explanation.
Fields: intent (naukri_auto_apply|naukri_search|youtube_search|google_search), job_title, location, max_apply (default 5), query.
User: {command}"""
    try:
        r=requests.post(OLLAMA_URL,json={"model":MODEL,"prompt":prompt,"stream":False},timeout=30)
        result=r.json()["response"].strip()
        if "```" in result:
            for p in result.split("```"):
                if "{" in p: result=p.strip().lstrip("json").strip(); break
        s=result.find("{"); e=result.rfind("}")+1
        if s!=-1: result=result[s:e]
        print(f"📋 {result}")
        return json.loads(result)
    except Exception as ex:
        print(f"❌ AI Error: {ex}"); return {"intent":"unknown"}

# ─────────────────────────────────────────────
# EXECUTE
# ─────────────────────────────────────────────
def execute(ai_result, page):
    intent=ai_result.get("intent","unknown")
    if intent=="naukri_auto_apply":
        n=int(ai_result.get("max_apply",5))
        if input(f"\n⚠️  Apply to {n} Naukri jobs (last 24h)? (yes/no): ").strip().lower() in ["yes","y"]:
            naukri_auto_apply(page,ai_result.get("job_title","java developer"),ai_result.get("location","any"),n)
        else: print("Cancelled.")
    elif intent=="naukri_search":
        naukri_search_only(page,ai_result.get("job_title","java developer"),ai_result.get("location","any"))
    elif intent=="youtube_search":
        safe_goto(page,f"https://www.youtube.com/results?search_query={ai_result.get('query','').replace(' ','+')}"); print("✅ YouTube!")
    elif intent=="google_search":
        safe_goto(page,f"https://www.google.com/search?q={ai_result.get('query','').replace(' ','+')}"); print("✅ Google!")
    else: print("⚠️ Try: 'auto apply java jobs on naukri'")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("="*60)
    print("  🤖 NAUKRI AGENT v4 — Smart Chatbot Handler")
    print("="*60)
    print(f"\n👤 {MY_PROFILE['name']} | {MY_PROFILE['current_role']} @ {MY_PROFILE['current_company']}")
    print(f"🔧 Key fix: AI now answers chatbot questions like")
    print(f"   'Did you work on any project?' → picks correct radio!\n")

    if not os.path.exists(MY_PROFILE["resume_path"]):
        print(f"⚠️  Resume not found: {MY_PROFILE['resume_path']}\n")

    with sync_playwright() as p:
        print("🚀 Opening browser...")
        browser=p.chromium.launch_persistent_context(
            user_data_dir=AGENT_PROFILE,channel="chrome",headless=False,slow_mo=100,
            args=["--start-maximized","--disable-blink-features=AutomationControlled"],
            no_viewport=True,ignore_default_args=["--enable-automation"],
        )
        page=browser.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        print("✅ Ready!\n")
        print("Commands:")
        print("  - auto apply java developer jobs on naukri")
        print("  - apply to 3 spring boot jobs on naukri")
        print("  - search java jobs on naukri\n")

        while True:
            command=input("🎤 Command (or 'quit'): ").strip()
            if command.lower() in ["quit","exit","q"]:
                print("👋 Goodbye!"); browser.close(); break
            if not command: continue
            ai_result=ask_ai(command)
            if ai_result.get("intent")=="unknown":
                print("❌ Could not understand."); continue
            try: execute(ai_result,page)
            except Exception as e: print(f"❌ Error: {e}")
            print("\n"+"-"*60+"\n✅ Ready!\n"+"-"*60+"\n")

if __name__=="__main__":
    main()