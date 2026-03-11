import matplotlib
try:
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    print("Matplotlib Agg backend loaded successfully")
    fig = plt.figure()
    print(f"Backend used: {matplotlib.get_backend()}")
except Exception as e:
    print(f"Error: {e}")
