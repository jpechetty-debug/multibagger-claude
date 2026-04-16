import pandas as pd
import requests
import io

def fetch_nifty500():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            # Column usually 'Symbol'
            symbols = df['Symbol'].tolist()
            # Append .NS
            ns_symbols = [f"{s}.NS" for s in symbols]
            
            # Read Config
            with open("config/config.yaml", "r") as f:
                lines = f.readlines()
            
            # Find markers
            start_idx = -1
            end_idx = -1
            
            for i, line in enumerate(lines):
                if line.strip().startswith("symbols:"):
                    start_idx = i
                if line.strip().startswith("# Trading Capital & Risk Management"):
                    end_idx = i
                    break
            
            if start_idx != -1 and end_idx != -1:
                new_lines = lines[:start_idx+1]
                for s in ns_symbols:
                    new_lines.append(f"  - \"{s}\"\n")
                new_lines.extend(lines[end_idx:])
                
                with open("config/config.yaml", "w") as f:
                    f.writelines(new_lines)
                print(f"Updated config.yaml with {len(ns_symbols)} symbols.")
            else:
                print("Could not find markers in config.yaml")

        else:
            print(f"Failed to fetch: {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_nifty500()
