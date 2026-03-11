
try:
    import matplotlib
    import matplotlib.pyplot as plt
    print(f"Matplotlib version: {matplotlib.__version__}")
    print(f"Matplotlib backend: {matplotlib.get_backend()}")
    
    fig = plt.figure()
    print("Figure created")
    
    plt.plot([1, 2, 3], [1, 2, 3])
    print("Plot command executed")
    
    plt.savefig("very_simple.png")
    print("Savefig executed")
    
    import os
    if os.path.exists("very_simple.png"):
        print("SUCCESS: File exists")
    else:
        print("FAILURE: File does not exist")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
