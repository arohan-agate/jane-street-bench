import os, json, pathlib, base64
from dotenv import load_dotenv
import pandas as pd
from PIL import Image
from openai import OpenAI

load_dotenv()
client = OpenAI()

df = pd.read_csv('data/puzzles/puzzles.csv')
record = df.iloc[0]

text = record['puzzleText']
name = record['name']

img_part = None
if bool(record['hasImage']):
    for ext in ('png', 'jpg', 'jpeg', 'PNG', 'JPG'):
        img_path = pathlib.Path(f'data/puzzles/puzzle_images/{name}/0_0.{ext}')
        if img_path.exists():
            b64 = base64.b64encode(img_path.read_bytes()).decode()
            img_part = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{ext};base64,{b64}"
                },
            }
            break

system_msg = {
    "role": "system",
    "content": "You are a puzzle solver. You will be given a puzzle and/or an accompanying image. Provide an answer to the puzzle and your step-by-step reasoning."
}

user_content = [{ "type": "text", "text": text }]
if img_part:
    user_content.append(img_part)

user_msg = { "role": "user", "content": user_content }
messages = [system_msg, user_msg]

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    temperature=0.25,
    max_tokens=1200,
)

print("\nMODEL ANSWER\n------------")
print(response.choices[0].message.content)

print("\nTOKENS  (for cost tracking)")
print(response.usage)

