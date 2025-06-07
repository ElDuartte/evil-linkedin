import time
import random
import json
import logging
import fitz  # PyMuPDF for PDF text extraction
import argparse
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Configuración de logging
logging.basicConfig(
    filename="bot_linkedin.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def procesar_cv(ruta_pdf):
    texto_completo = ""
    try:
        doc = fitz.open(ruta_pdf)
        for page in doc:
            texto_completo += page.get_text()
        doc.close()
    except Exception as e:
        logging.error(f"Error al leer el PDF {ruta_pdf}: {e}")
        return [], {}
    if not texto_completo.strip():
        logging.warning(
            "El CV parece no contener texto (posible PDF escaneado). Considere usar OCR."
        )
    texto_min = texto_completo.lower().replace("\n", " ")
    texto_min = re.sub(r"[^\w\s]", " ", texto_min)
    palabras = texto_min.split()
    stopwords = {
        "de",
        "la",
        "que",
        "el",
        "en",
        "y",
        "a",
        "los",
        "del",
        "se",
        "las",
        "por",
        "un",
        "para",
        "con",
        "una",
        "su",
        "the",
        "and",
        "of",
        "to",
        "in",
        "for",
        "on",
        "at",
        "by",
    }
    palabras = [w for w in palabras if w not in stopwords and len(w) > 2]
    if not palabras:
        return [], {}
    freq = {}
    for w in palabras:
        freq[w] = freq.get(w, 0) + 1
    palabras_ordenadas = sorted(freq, key=freq.get, reverse=True)
    palabras_clave = palabras_ordenadas[:20]
    logging.info(f"Palabras clave extraídas del CV: {palabras_clave}")
    datos = {}
    email_match = re.search(
        r"[A-Za-z0-9\._%+-]+@[A-Za-z0-9\.-]+\.[A-Za-z]{2,}", texto_completo
    )
    if email_match:
        datos["email"] = email_match.group(0)
    phone_match = re.search(r"\+?\d[\d\-\s]{7,}\d", texto_completo)
    if phone_match:
        datos["telefono"] = phone_match.group(0)
    nombre_match = texto_completo.strip().split("\n")[0]
    if 2 <= len(nombre_match.split()) <= 5:
        datos["nombre"] = nombre_match
    logging.info(f"Datos personales extraídos del CV: {datos}")
    return palabras_clave, datos


def iniciar_navegador(cookies_path=None):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    if cookies_path and os.path.exists(cookies_path):
        try:
            driver.get("https://www.linkedin.com/")
            with open(cookies_path, "r") as f:
                cookies = json.load(f)
            for cookie in cookies:
                if "domain" in cookie and "linkedin.com" in cookie["domain"]:
                    driver.add_cookie(cookie)
            driver.refresh()
            logging.info("Cookies cargadas correctamente.")
        except Exception as e:
            logging.error(f"Error al cargar cookies: {e}")
    else:
        logging.warning("No se proporcionaron cookies o el archivo no existe.")

    return driver


def buscar_empleos(driver, palabras_clave_busqueda, ubicacion, dias):
    base_url = "https://www.linkedin.com/jobs/search/?f_LF=f_AL"
    if dias:
        segundos = dias * 86400
        base_url += f"&f_TPR=r{segundos}"
    if palabras_clave_busqueda:
        from urllib.parse import quote_plus

        base_url += f"&keywords={quote_plus(palabras_clave_busqueda)}"
    if ubicacion:
        from urllib.parse import quote_plus

        base_url += f"&location={quote_plus(ubicacion)}"
    base_url += "&sortBy=DD"
    logging.info(f"Navegando a la URL de búsqueda: {base_url}")
    driver.get(base_url)
    time.sleep(random.uniform(3, 6))
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "jobs-search-results"))
        )
    except TimeoutException:
        logging.error("La página de resultados de empleo no cargó a tiempo.")
        return []
    job_elems = driver.find_elements(By.CSS_SELECTOR, "ul.jobs-search-results__list li")
    logging.info(f"{len(job_elems)} empleos encontrados.")
    return job_elems


def postular_a_empleo(driver, job_elem, palabras_clave_cv, datos_cv):
    try:
        driver.execute_script("arguments[0].scrollIntoView();", job_elem)
        job_elem.click()
    except Exception as e:
        logging.error(f"No se pudo hacer click en el empleo: {e}")
        return False
    time.sleep(random.uniform(2, 4))
    try:
        titulo = driver.find_element(By.CSS_SELECTOR, "h2.topcard__title").text.strip()
    except:
        titulo = "(título no encontrado)"
    try:
        empresa = driver.find_element(
            By.CSS_SELECTOR, "span.topcard__flavor"
        ).text.strip()
    except:
        empresa = "(empresa no encontrada)"
    descripcion = ""
    try:
        ver_mas_btn = driver.find_elements(
            By.CSS_SELECTOR, "button[data-control-name='show_more_description']"
        )
        if ver_mas_btn:
            ver_mas_btn[0].click()
            time.sleep(1)
        descripcion = driver.find_element(
            By.CLASS_NAME, "jobs-description__content"
        ).text.lower()
    except NoSuchElementException:
        logging.warning(
            f"No se pudo extraer la descripción para {titulo} en {empresa}."
        )
    porcentaje_match = 0
    if descripcion and palabras_clave_cv:
        palabras_desc = set(re.sub(r"[^\w\s]", " ", descripcion).split())
        coincidencias = [w for w in palabras_clave_cv if w in palabras_desc]
        porcentaje_match = int((len(coincidencias) / len(palabras_clave_cv)) * 100)
    logging.info(
        f'Postulando a "{titulo}" en "{empresa}". Coincidencia: {porcentaje_match}%'
    )
    try:
        easy_apply_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.jobs-apply-button"))
        )
        easy_apply_btn.click()
    except Exception as e:
        logging.error(f"No se pudo hacer click en Easy Apply: {e}")
        return False
    time.sleep(random.uniform(2, 4))
    try:
        phone_inputs = driver.find_elements(By.CSS_SELECTOR, "input[id*=phone]")
        for inp in phone_inputs:
            if inp.get_attribute("value") == "" and datos_cv.get("telefono"):
                inp.send_keys(datos_cv["telefono"])
        submit_btns = driver.find_elements(
            By.CSS_SELECTOR, "button[aria-label^='Submit application']"
        )
        if submit_btns:
            submit_btns[0].click()
        else:
            logging.warning("No se encontró el botón de enviar.")
            return False
    except Exception as e:
        logging.error(f"Error al completar el formulario: {e}")
        return False
    time.sleep(random.uniform(1, 3))
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot de Easy Apply de LinkedIn")
    parser.add_argument(
        "--cv", dest="cv_path", required=True, help="Ruta al archivo PDF del CV"
    )
    parser.add_argument(
        "--cookies", dest="cookies_path", help="Ruta al archivo JSON con cookies"
    )
    parser.add_argument(
        "--max",
        dest="max_apply",
        type=int,
        default=5,
        help="Número máximo de aplicaciones",
    )
    parser.add_argument(
        "--salario",
        dest="salario_min",
        type=int,
        default=0,
        help="Salario mínimo deseado",
    )
    parser.add_argument(
        "--dias",
        dest="dias",
        type=int,
        default=0,
        help="Filtrar empleos por días recientes",
    )
    parser.add_argument(
        "--puesto",
        dest="palabras_busqueda",
        type=str,
        default="",
        help="Palabras clave del puesto",
    )
    parser.add_argument(
        "--ubicacion",
        dest="ubicacion",
        type=str,
        default="",
        help="Ubicación del empleo",
    )
    args = parser.parse_args()

    cv_path = args.cv_path
    cookies_path = args.cookies_path
    max_apply = args.max_apply
    salario_minimo = args.salario_min
    dias = args.dias
    palabras_busqueda = args.palabras_busqueda
    ubicacion = args.ubicacion

    palabras_clave_cv, datos_cv = procesar_cv(cv_path)
    driver = iniciar_navegador(cookies_path=cookies_path)
    job_elements = buscar_empleos(driver, palabras_busqueda, ubicacion, dias)

    aplicaciones_realizadas = 0
    for job in job_elements:
        if aplicaciones_realizadas >= max_apply:
            break
        resultado = postular_a_empleo(driver, job, palabras_clave_cv, datos_cv)
        if resultado:
            aplicaciones_realizadas += 1
            time.sleep(random.uniform(5, 10))
    logging.info(f"Total aplicaciones enviadas: {aplicaciones_realizadas}")
    driver.quit()
