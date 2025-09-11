import os
import sys
import requests
from langchain_community.document_loaders import CSVLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.logger import logging
from src.exception import CustomException
from src.utils import get_file_path

class RAGPipeline:
    """
    Manages the creation and retrieval of a vector database for the RAG agent.
    """

    def __init__(self, data_source=None, chroma_db_path="chroma_db", embedding_model="nomic-embed-text"):
        # Use the default eda_knowledge_base.csv if no data_source is provided
        self.data_source = data_source if data_source else os.path.join('src', 'pipeline', 'eda_knowledge_base.csv')
        self.chroma_db_path = chroma_db_path
        self.embedding_model = embedding_model

    def _build_vector_db(self):
        """
        Builds the vector database if it doesn't already exist.
        """
        logging.info(f"Loading data from '{self.data_source}'...")
        loader = CSVLoader(file_path=self.data_source, encoding="utf-8")
        documents = loader.load()

        logging.info("Splitting documents into chunks...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_documents(documents)

        try:
            logging.info(f"Initializing embedding model: '{self.embedding_model}'...")
            embeddings = OllamaEmbeddings(model=self.embedding_model)

            logging.info("Creating and persisting the vector store... (This may take a moment)")
            db = Chroma.from_documents(
                chunks,
                embeddings,
                persist_directory=self.chroma_db_path
            )
            logging.info(f"Knowledge base built and saved to '{self.chroma_db_path}'.")

        except ValueError as e:
            # Catch the specific error for a missing model
            if "not found, try pulling it first" in str(e):
                error_msg = (
                    f"The embedding model '{self.embedding_model}' was not found by the Ollama server.\n"
                    "Please pull the model by running the following command in your terminal:\n\n"
                    f"ollama pull {self.embedding_model}\n"
                )
                print("\n" + "="*80)
                print("🛑 Ollama Model Not Found")
                print("-" * 80)
                print(error_msg)
                print("="*80 + "\n")
            raise CustomException(e, sys)
        except Exception as e:
            raise CustomException(e, sys)

    def get_retriever(self):
        """
        Ensures the vector DB is built and returns a retriever object.
        """
        if not os.path.exists(self.chroma_db_path):
            logging.warning(f"ChromaDB not found at '{self.chroma_db_path}'. Building it now.")
            self._build_vector_db()
        else:
            logging.info(f"Found existing ChromaDB at '{self.chroma_db_path}'. Loading it.")

        try:
            embeddings = OllamaEmbeddings(model=self.embedding_model)
            db = Chroma(persist_directory=self.chroma_db_path, embedding_function=embeddings)
            return db.as_retriever(search_kwargs={'k': 5})

        except Exception as e:
            raise CustomException(e, sys)