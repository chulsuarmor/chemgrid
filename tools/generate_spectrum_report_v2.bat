@echo off
echo Testing Spectrum PDF Exporter...
call C:\ProgramData\anaconda3\Scripts\activate.bat chemgrid
python agents/09_data_export/spectrum_pdf_exporter.py
echo.
echo ===================================================
echo Report generated in: docs\exports\spectra_assets\auto_generated
echo Opening output folder...
echo ===================================================
start explorer "docs\exports\spectra_assets\auto_generated"
pause
