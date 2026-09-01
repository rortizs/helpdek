@echo off\nif "%1"=="run" (if "%2"=="pytest" (python -m pytest %3))
