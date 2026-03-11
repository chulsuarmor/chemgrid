@echo off
echo Starting Exporter...
python --version > exporter_version.log 2>&1
echo Running with python...
python agents/09_data_export/spectrum_pdf_exporter.py > exporter_output.log 2>&1

if %errorlevel% neq 0 (
    echo Python command failed or script error. Trying 'py' launcher...
    py agents/09_data_export/spectrum_pdf_exporter.py > exporter_output.log 2>&1
)
echo Done.
