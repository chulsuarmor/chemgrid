$fp = 'c:\chemgrid\src\app\spectrum_pdf_exporter.py' 
$src = [System.IO.File]::ReadAllText($fp, [System.Text.Encoding]::UTF8) 
$nl = [Environment]::NewLine 
$anchor = "except ImportError:" + $nl + "    MATPLOTLIB_AVAILABLE = False" 
$insert = $nl + $nl 
$insert += "# Korean font registration for PDF output" + $nl 
$insert += "def _register_korean_font():" + $nl 
$insert += "    " + '"""' + "Register Korean font for PDF. Returns font name to use." + '"""' + $nl 
$insert += "    try:" + $nl 
$insert += "        from reportlab.pdfbase import pdfmetrics" + $nl 
$insert += "        from reportlab.pdfbase.ttfonts import TTFont" + $nl 
$insert += "        import os" + $nl 
$insert += "        for fp, name in [" + $nl 
$insert += "            ('C:/Windows/Fonts/malgun.ttf', 'Malgun')," + $nl 
$insert += "            ('C:/Windows/Fonts/malgunbd.ttf', 'MalgunBold')," + $nl 
$insert += "            ('C:/Windows/Fonts/gulim.ttc', 'Gulim')," + $nl 
$insert += "        ]:" + $nl 
$insert += "            if os.path.exists(fp):" + $nl 
$insert += "                try:" + $nl 
$insert += "                    pdfmetrics.registerFont(TTFont(name, fp))" + $nl 
$insert += "                    return name" + $nl 
$insert += "                except Exception:" + $nl 
$insert += "                    continue" + $nl 
$insert += "    except ImportError:" + $nl 
$insert += "        pass" + $nl 
$insert += "    return 'Helvetica'" + $nl 
$insert += $nl 
$insert += "KOREAN_FONT = _register_korean_font()" + $nl 
$insert += $nl 
$insert += "# Shoolery's Rule: delta(H) = 0.23 + sum of substituent constants" + $nl 
$insert += "SHOOLERY_INCREMENTS = {" + $nl 
$insert += "    'CH3': 0.0, 'CH2': 0.0, 'CH': 0.0," + $nl 
$insert += "    'C=O_ketone': 1.50, 'C=O_ester': 1.21, 'COOH': 1.00," + $nl 
$insert += "    'OH': 2.56, 'OR': 2.36, 'NH2': 1.57, 'NR2': 1.57," + $nl 
$insert += "    'Cl': 2.53, 'Br': 2.33, 'F': 3.30, 'I': 2.24," + $nl 
$insert += "    'Ph': 1.85, 'C=C': 1.32, 'C" + [char]0x2261 + "C': 1.44," + $nl 
$insert += "    'NO2': 3.36, 'CN': 1.70, 'S': 1.64," + $nl 
$insert += "}" + $nl 
$newsrc = $src.Replace($anchor, $anchor + $insert) 
$old1 = "('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold')" 
$new1 = "('FONTNAME', (0, 0), (0, -1), KOREAN_FONT)" 
$old2 = "('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold')" 
$new2 = "('FONTNAME', (0, 0), (-1, 0), KOREAN_FONT)" 
$newsrc = $newsrc.Replace($old1, $new1) 
$newsrc = $newsrc.Replace($old2, $new2) 
[System.IO.File]::WriteAllText($fp, $newsrc, [System.Text.Encoding]::UTF8) 
Write-Host "Done. New size: $($newsrc.Length)"  
Write-Host "KOREAN_FONT: $($newsrc.Contains('KOREAN_FONT'))"  
Write-Host "HB remaining: $(([regex]::Matches($newsrc, 'Helvetica-Bold')).Count)" 
