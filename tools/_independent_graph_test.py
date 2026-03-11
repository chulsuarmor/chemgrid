
try:
    import sys
    import os
    
    # Add CWD to path
    sys.path.append(os.getcwd())
    
    print("Testing Matplotlib Graph Generation independently...")
    
    import matplotlib.pyplot as plt
    import numpy as np
    
    # Create a simple figure
    fig = plt.figure(figsize=(10, 6), dpi=300)
    ax = fig.add_subplot(111)
    
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    ax.plot(x, y)
    
    # Save it
    output_path = "independent_matplotlib_test.png"
    plt.savefig(output_path)
    print(f"Independent test saved to {output_path}")
    
    if os.path.exists(output_path):
        print("File verification: EXISTS")
    else:
        print("File verification: MISSING")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
