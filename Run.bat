@echo off
title Discord Bot - Override

REM Vai para a pasta do bot
cd /d C:\Users\Adryan\Desktop\Override

REM Ativa o ambiente virtual
call venv\Scripts\activate

python argos_setup.py

REM Inicia o bot
python main.py

REM Mantém a janela aberta se der erro
pause
