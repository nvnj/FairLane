from phoenix.client import Client
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

def main():
    client = Client()
    df = client.spans.get_spans_dataframe(project_name="FairLane")
    
    if df.empty:
        print("No spans found.")
        return

    # Print a few rows of columns that start with 'attributes.'
    attr_cols = [c for c in df.columns if c.startswith('attributes.')]
    print("Found attribute columns:", attr_cols)
    
    # Check for 'experiment' specifically
    exp_related = [c for c in df.columns if 'experiment' in c]
    print("Experiment related columns:", exp_related)
    
    # Sample data
    if exp_related:
        print("\nSample data for experiment related columns:")
        print(df[exp_related].dropna().head(20))

    # Check for judge_score
    if 'attributes.judge_score' in df.columns:
        print("\nSample data for judge_score:")
        print(df['attributes.judge_score'].dropna().head(20))

if __name__ == "__main__":
    main()
