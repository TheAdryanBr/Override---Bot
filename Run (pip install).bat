@echo off
title Discord Bot - Override
cd /d C:\Users\Adryan\Desktop\Override

REM Ativa o venv
call venv\Scripts\activate.bat

REM Atualiza pip e instala deps
python -m pip install -U pip
pip install -r requirements.txt

REM Instala pacote do Argos (pode rodar sempre, mas normalmente so precisa 1x)
python argos_setup.py

REM Inicia o bot
python main.py

pause
