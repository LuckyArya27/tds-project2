# ///script
# requires-python= ">=3.11"
# dependencies = [
#     "pandas",
#     "seaborn",
#     "matplotlib",
#     "httpx",
#     "chardet",
#     "dotenv",
#     "asyncio"
# ]
# ///


import glob
import os
import sys
import pandas as pd
import seaborn as sns
import matplotlib
import asyncio
import httpx
import chardet
from dotenv import load_dotenv
matplotlib.use('Agg')
import matplotlib.pyplot as plt

load_dotenv()

API_URL = 'https://aiproxy.sanand.workers.dev/openai/v1/chat/completions'
AIPROXY_TOKEN = os.getenv('AIPROXY_TOKEN')
print(f"AIPROXY_TOKEN: {AIPROXY_TOKEN}")

def loadData(file_path):
    """Load data from a CSV file with encoding detection."""
    if not os.path.isfile(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    with open(file_path, 'rb') as f:
        rawdata = chardet.detect(f.read())
    encoding = rawdata.get('encoding', 'utf-8')  # Default to UTF-8 if encoding detection fails
    print(f"Detected file encoding: {encoding}")

    try:
        return pd.read_csv(file_path, encoding=encoding)
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        sys.exit(1)

def performAutolysis(data_frame):
    """Perform analysis on numerical data in the DataFrame."""
    if data_frame.empty:
        print("Error: The dataset is empty.")
        sys.exit(1)

    numerical_data = data_frame.select_dtypes(include=['number'])

    # Calculate variance and filter significant columns
    variance = numerical_data.var()
    significant_columns = variance[variance > 0.01].index

    if significant_columns.empty:
        print("No columns with significant variance were found.")
        return {
            'summary': {},
            'missing_values': {},
            'correlation': {}
        }

    significant_data = numerical_data[significant_columns]

    analysis_results = {
        'summary': significant_data.describe().to_dict(),
        'missing_values': significant_data.isnull().sum().to_dict(),
        'correlation': significant_data.corr().to_dict()
    }

    print("Data analysis completed.")
    return analysis_results

def createPlots(data_frame, output_dir):
    """Create and save important plots for numerical columns and return a list of plot file paths."""
    sns.set(style='whitegrid')
    numerical_columns = data_frame.select_dtypes(include=['number']).columns
    plot_file_paths = []

    if numerical_columns.empty:
        print("No numerical columns found for visualization.")
        return plot_file_paths

    # Calculate variance for numerical columns
    variance = data_frame[numerical_columns].var()

    # Filter significant columns based on variance
    significant_columns = variance[variance > 0.01].index  # Get only column names with significant variance

    if significant_columns.empty:
        print("No significant numerical columns found for plotting.")
        return plot_file_paths

    for column in significant_columns:
        plt.figure()
        sns.histplot(data_frame[column].dropna(), kde=True)
        plt.title(f"Distribution of {column}")
        plt.xlabel(column)
        plt.ylabel("Frequency")
        plt.legend()
        file_name = os.path.join(output_dir, f"{column}_distribution.png")
        try:
            plt.savefig(file_name)
            plot_file_paths.append(file_name)  # Add the plot path to the list
            print(f"Saved distribution plot: {file_name}")
        except Exception as e:
            print(f"Error saving plot for {column}: {e}")
        finally:
            plt.close()

    return plot_file_paths

async def generateNarrative(analysis_data, plot_file_paths):
    """Generate a narrative using the LLM based on analysis results and visualizations."""
    if not AIPROXY_TOKEN:
        print("Error: AIPROXY_TOKEN environment variable is not set.")
        sys.exit(1)

    significant_analysis = {
        'summary': analysis_data['summary'],
        'missing_values': {k: v for k, v in analysis_data['missing_values'].items() if v > 0},
        'correlation': analysis_data['correlation']
    }

    if not significant_analysis['summary']:
        print("No significant analysis to generate narrative.")
        return "No meaningful insights to generate narrative."

    headers = {
        'Authorization': f"Bearer {AIPROXY_TOKEN}",
        'Content-Type': 'application/json'
    }

    plot_descriptions = "\n".join([f"- {plot_path}" for plot_path in plot_file_paths]) if plot_file_paths else "No visualizations available."
    prompt_message = f"""
    Provide a detailed analysis based on the following significant data insights:
    Summary: {significant_analysis['summary']}
    Missing values: {significant_analysis['missing_values']}
    Correlations: {significant_analysis['correlation']}
    
    Additionally, consider the following visualizations for insights:
    {plot_descriptions}
    """

    request_data = {
        'model': 'gpt-4o-mini',
        'messages': [{'role': 'user', 'content': prompt_message}]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, headers=headers, json=request_data, timeout=60)
            response.raise_for_status()
            narrative = response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No narrative generated.')
            if narrative:
                print("Narrative generated successfully.")
                return narrative
    except httpx.RequestError as e:
        print(f"Request Error: {e}")
        print(f"Request Details: {e.request}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP Status Error: {e}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

    return "Narrative generation failed due to an error."

async def mainProcess(file_path):
    """Main function to run the autolysis process."""
    print("Starting the autolysis process...")

    # If '*' is entered, gather all .csv files in the current directory
    if file_path == '*':
        print("Processing all CSV files in the current directory...")
        # Get a list of all CSV files in the current directory
        file_paths = glob.glob("datasets/*.csv")
        if not file_paths:
            print("Error: No CSV files found in the current directory.")
            sys.exit(1)
    else:
        # Process the single file specified by the user
        file_paths = [file_path]

    for file_path in file_paths:
        print(f"Processing file: {file_path}")

        # Create output directory based on the CSV file name
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = base_name
        os.makedirs(output_dir, exist_ok=True)

        # Load the dataset
        data = loadData(file_path)
        print("Dataset loaded successfully.")

        # Perform analysis
        print("Performing data analysis...")
        analysis_results = performAutolysis(data)

        # Create visualizations
        print("Generating visualizations...")
        plot_file_paths = createPlots(data, output_dir)

        # Generate narrative
        print("Generating narrative...")
        narrative = await generateNarrative(analysis_results, plot_file_paths)

        if narrative != "Narrative generation failed due to an error.":
            readme_path = os.path.join(output_dir, 'README.md')
            try:
                with open(readme_path, 'w') as f:
                    f.write(narrative)
                print(f"Narrative successfully saved to {readme_path}.")
            except Exception as e:
                print(f"Error saving narrative: {e}")
        else:
            print("Failed to generate narrative. Skipping README creation.")

        print("Autolysis process completed.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python autolysis.py <file_path>")
        sys.exit(1)

    asyncio.run(mainProcess(sys.argv[1]))
