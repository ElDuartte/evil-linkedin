import logging
from dotenv import load_dotenv

# Setup basic logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s"
)

load_dotenv()  # reads the .env file into os.environ

import os
import time
import csv
import datetime
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Optional PDF parsing
try:
    from PyPDF2 import PdfReader

    PDF_SUPPORTED = True
except ModuleNotFoundError:
    logging.warning("PyPDF2 not installed; PDF resumes treated as plain text.")
    PDF_SUPPORTED = False

# Predefined list of common technologies to scan for
COMMON_TECHSKILLS = [
    "JavaScript",
    "Ruby",
    "Rails",
    "React",
    "Angular",
    "Vue",
    "Node.js",
    "HTML",
    "CSS",
    "TypeScript",
    "SQL",
    "NoSQL",
    "MongoDB",
    "PostgreSQL",
]


class LinkedInApplyBot:
    def __init__(
        self,
        email,
        password,
        resume_path_es,
        resume_path_en,
        headless=True,
        max_applications=None,
        output_csv="applied_jobs.csv",
        cookies_file="linkedin_cookies.pkl",
    ):
        logging.debug("Initializing LinkedInApplyBot")
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        self.email = email
        self.password = password
        self.resume_path_es = resume_path_es
        self.resume_path_en = resume_path_en
        self.max_applications = max_applications
        self.output_csv = output_csv
        self.cookies_file = cookies_file
        self.min_salary = int(os.getenv("MIN_SALARY", "0"))

        # ensure CSV header exists
        if not os.path.isfile(self.output_csv):
            logging.debug("Creating CSV log file and header")
            with open(self.output_csv, mode="w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "job title",
                        "technologies",
                        "years_experience",
                        "date of apply",
                        "job link",
                    ]
                )

    def login(self):
        logging.debug("Logging into LinkedIn as %s", self.email)
        self.driver.get("https://www.linkedin.com/login")
        # try loading cookies
        if os.path.isfile(self.cookies_file):
            try:
                with open(self.cookies_file, "rb") as cf:
                    cookies = pickle.load(cf)
                for c in cookies:
                    self.driver.add_cookie(c)
                self.driver.get("https://www.linkedin.com/feed")
                time.sleep(3)
                logging.debug("Loaded session cookies successfully")
                return
            except Exception as e:
                logging.warning("Failed to load cookies: %s", e)
        # manual login
        time.sleep(2)
        self.driver.find_element(By.ID, "username").send_keys(self.email)
        self.driver.find_element(By.ID, "password").send_keys(
            self.password + Keys.RETURN
        )
        time.sleep(5)
        logging.debug("Login complete, saving cookies to %s", self.cookies_file)
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, "wb") as cf:
                pickle.dump(cookies, cf)
        except Exception as e:
            logging.warning("Failed to save cookies: %s", e)

    def extract_skills(self, top_n=5):
        logging.debug("Extracting skills from resumes")
        text = ""
        for path in (self.resume_path_es, self.resume_path_en):
            try:
                if PDF_SUPPORTED and path.lower().endswith(".pdf"):
                    reader = PdfReader(path)
                    for page in reader.pages:
                        text += page.extract_text() or ""
                else:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text += f.read()
            except Exception:
                continue
        skills = []
        lower = text.lower()
        for tech in COMMON_TECHSKILLS:
            if tech.lower() in lower:
                skills.append(tech)
            if len(skills) >= top_n:
                break
        logging.debug("Extracted skills: %s", skills)
        return skills

    def dump_page_html(self, filename):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logging.info("HTML dumped to %s", filename)
        except Exception as e:
            logging.error("Failed dumping HTML: %s", e)

    def analyze_first_card(self):
        try:
            card = self.driver.find_element(
                By.CSS_SELECTOR, "ul.jobs-search__results-list li"
            )
            snippet = card.get_attribute("innerHTML")
            logging.info("First card HTML snippet: %s", snippet[:500])
        except Exception as e:
            logging.error("First card analysis failed: %s", e)

    def search_jobs(self, keyword, location="Spain", date_posted="24h", pages=1):
        url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}&f_AL=true"
        if date_posted == "24h":
            url += "&f_TP=1"
        logging.debug("Searching %s", url)
        self.driver.get(url)
        time.sleep(5)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        cards = self.driver.find_elements(
            By.CSS_SELECTOR, "ul.jobs-search__results-list li"
        )
        if not cards:
            self.dump_page_html("search_no_cards.html")
            self.analyze_first_card()
            return []
        results = []
        for card in cards:
            try:
                title = card.find_element(By.TAG_NAME, "h3").text
                link = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                results.append((title, link))
            except:
                continue
        logging.info("Found %d jobs for %s", len(results), keyword)
        return results

    def apply_to_jobs(self, jobs):
        today = datetime.date.today().isoformat()
        exp = 0  # placeholder for years experience
        for idx, (title, link) in enumerate(jobs, 1):
            self.driver.get(link)
            time.sleep(3)
            try:
                btn = self.driver.find_element(
                    By.CSS_SELECTOR, "button.jobs-apply-button"
                )
                btn.click()
                time.sleep(2)
                # dump form on click
                self.dump_page_html(f"form_{idx}.html")
                # contact info step
                try:
                    header = self.driver.find_elements(
                        By.XPATH,
                        "//h3[contains(text(),'Información de contacto') or contains(text(),'Contact information')]",
                    )
                    if header:
                        nxt = self.driver.find_element(
                            By.XPATH,
                            "//button[contains(text(),'Siguiente') or contains(text(),'Next')]",
                        )
                        nxt.click()
                        time.sleep(2)
                except:
                    pass
                # language resume selection skipped (already on LinkedIn)
                # additional questions: years exp
                try:
                    exp_input = self.driver.find_element(
                        By.CSS_SELECTOR, "input[type='text']"
                    )
                    exp = len(
                        self.resume_path_es
                    )  # placeholder; implement extract_experience
                    exp_input.send_keys(str(exp))
                except:
                    pass
                # job permit question
                try:
                    yes = self.driver.find_element(
                        By.XPATH, "//input[@type='radio' and @value='Yes']"
                    )
                    yes.click()
                except:
                    pass
                # submit
                submit = self.driver.find_element(
                    By.CSS_SELECTOR, "button[aria-label*='Submit']"
                )
                submit.click()
                logging.info("Applied to %s", title)
                with open(self.output_csv, "a", newline="") as f:
                    csv.writer(f).writerow(
                        [title, ",".join(COMMON_TECHSKILLS), exp, today, link]
                    )
            except Exception as e:
                logging.error("Apply failed for %s: %s", title, e)

    def quit(self):
        self.driver.quit()


if __name__ == "__main__":
    EMAIL = os.getenv("LINKEDIN_EMAIL")
    PASSWORD = os.getenv("LINKEDIN_PASSWORD")
    RESUME_ES = os.getenv("RESUME_PATH_ES")
    RESUME_EN = os.getenv("RESUME_PATH_EN")

    bot = LinkedInApplyBot(
        email=EMAIL,
        password=PASSWORD,
        resume_path_es=RESUME_ES,
        resume_path_en=RESUME_EN,
        headless=False,
        max_applications=5,
    )
    bot.login()
    skills = bot.extract_skills()
    for tech in skills:
        jobs = bot.search_jobs(tech)
        bot.apply_to_jobs(jobs)
    bot.quit()
