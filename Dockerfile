FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Dependencias necesarias para Chromium + Selenium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    chromium \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium

# Establece el directorio de trabajo
WORKDIR /app

# Copia el código fuente
COPY . /app

# Instala dependencias de Python
RUN pip install --upgrade pip && pip install selenium webdriver-manager PyMuPDF

# Comando por defecto
CMD ["python", "test.py"]
