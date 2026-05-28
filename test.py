from google import genai
import os

client = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"], location="us-central1")

try:
  # Attempt to retrieve information about the model
  model_info = client.models.get(model="google/gemini-3.5-flash@default")
  print(f"Successfully found model: {model_info.name}")
except Exception as e:
  print(f"Error finding model: {e}")
