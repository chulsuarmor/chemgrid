import base64 
fp = r'c:\chemgrid\src\app\popup_3d.py' 
src = open(fp, encoding='utf-8').read() 
method = ( 
"    def _load_estimated_vibrations(self, smiles: str):\n" 
