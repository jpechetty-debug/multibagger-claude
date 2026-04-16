import sys
import os

# Ensure we can import the modules
sys.path.append(os.path.join(os.getcwd(), 'src'))

print("Running Demo Backtest...")
os.system("python run_backtest.py")
print("Demo Complete. Check sample_output.csv")
