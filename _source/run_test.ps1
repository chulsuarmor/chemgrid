# PowerShell script to run test and save output
$testPath = "C:\Users\김남헌\Desktop\organicdraw\_source\test_parser_standalone.py"
$outputPath = "C:\Users\김남헌\Desktop\organicdraw\_source\test_results.txt"

python $testPath 2>&1 | Out-File -Encoding UTF8 $outputPath
Write-Host "Test completed. Results saved to $outputPath"
