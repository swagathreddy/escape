# import requests
# import base64
# from PIL import Image
# import io

# def generate_image(prompt):
#     api_key = "sk-riYIH1F1xttQQnZQfK1GWZsCWSbVYP5WTK2NZRBBLo2pBr7F"
#     url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {api_key}"
#     }
    
#     payload = {
#         "text_prompts": [{"text": prompt}],
#         "cfg_scale": 7,
#         "height": 1024,
#         "width": 1024,
#         "samples": 1
#     }
    
#     response = requests.post(url, headers=headers, json=payload)
    
#     # Check if request was successful
#     if response.status_code == 200:
#         # Decode base64 image
#         image_base64 = response.json()['artifacts'][0]['base64']
#         image_data = base64.b64decode(image_base64)
        
#         # Convert to PIL Image
#         image = Image.open(io.BytesIO(image_data))
        
#         # Save image
#         image.save("generated_image.png")
        
#         # Display image
#         image.show()
        
#         return image
#     else:
#         print(f"Error: {response.status_code}")
#         print(response.text)
#         return None

# # Usage
# image = generate_image("A mysterious vintage safe with intricate lock, dramatic lighting, dark background, detailed texture, photorealistic")




import requests

API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
headers = {"Authorization": "Bearer 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"}

def query(payload):
	response = requests.post(API_URL, headers=headers, json=payload)
	return response.content

image_bytes = query({
	"inputs": "fallen_log image",
})

# You can access the image with PIL.Image for example
import io
from PIL import Image
image = Image.open(io.BytesIO(image_bytes))
image.show()