$src = 'c:\chemgrid\src\app\popup_3d.py' 
[System.Console]::OutputEncoding=[System.Text.Encoding]::UTF8  
$c = [System.IO.File]::ReadAllText($src, [System.Text.Encoding]::UTF8)  
Write-Output ('Len:'+$c.Length) 
