import os
import sys
from langchain_groq.chat_models import ChatGroq
from langchain_ollama.chat_models import ChatOllama
from src.logger import logging
from src.exception import CustomException
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

def get_file_path(folder='data'):
    
    try:
        logging.info("Process of dataset retrieving has begun.")

        for file in os.listdir(folder):
            if file.endswith('.csv'):
            
                logging.info("Dataset's path is retrieved successfully")
                return os.path.join(folder, file)

        return None
    
    except Exception as e:
        raise CustomException(e, sys)

def get_llm(llm_type: str):
    
    try:
        logging.info("Choosing an LLM Model.")

        if llm_type == "Groq" or llm_type == "groq":
            llm = ChatGroq(model = "llama-3.1-8b-instant", temperature = 1)
            logging.info("LLM Model: {llm} has been choosen.")
            return llm
        
        elif llm_type == "Ollama" or llm_type == "ollama":
            llm = ChatOllama(model = "qwen3:4b", temperature = 1)
            logging.info("LLM Model: {llm} has been choosen.")
            return llm

        else:
            logging.info("LLM Model not available for that type.")
            return None

    except Exception as e:
        raise CustomException(e, sys)
    
def get_dataset(file_path: str):
    
    try:
        return pd.read_csv(file_path)
    
    except Exception as e:
        
        raise CustomException(e, sys)
    
def save_dataset(file, filename='dataset.csv'):
    # Create a 'data' directory if it doesn't exist
    data_dir = 'data'
    os.makedirs(data_dir, exist_ok=True)
    
    # Read the uploaded file and save it to the 'data' folder
    df = pd.read_csv(file)
    save_path = os.path.join(data_dir, filename)
    df.to_csv(save_path, index=False)
    
    logging.info(f"Dataset is successfully saved in the folder named 'data' with path {save_path}")

    return save_path