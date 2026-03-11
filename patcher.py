import sys,shutil,re 
sys.stdout.reconfigure(encoding='utf-8')  
S=r'c:/chemgrid/src/app/popup_3d.py'  
c=open(S,encoding='utf-8').read()  
shutil.copy2(S,S+'.bak')  
print('Backup done, len=',len(c)) 
