from PIL import Image
import requests
from io import BytesIO
import imgbbpy

def create_image(skin_url) -> Image:
    response = requests.get(skin_url)
    img_data = response.content

    image = Image.open(BytesIO(img_data)) # should be size 180x432

    background_image = Image.new('RGBA', (240, 492), color=(0,0,0,0))

    # Calculate the position to paste the overlay image in the center of the background image
    x_position = (background_image.width - image.width) // 2
    y_position = (background_image.height - image.height) // 2

    # Paste the overlay image on the center of the background image
    background_image.paste(image, (x_position, y_position))

    # Crop the top part to get a 200x200 image
    cropped_image = background_image.crop((0, 0, 240, 240))
    return cropped_image


def get_avatar_url(mc_name, imgbb_key):
    skin_url = "https://mc-heads.net/body/" + mc_name
    img = create_image(skin_url)
    img.save("temp.png")
    client = imgbbpy.SyncClient(imgbb_key)
    uploaded_image = client.upload(file='temp.png', name=mc_name)
    return uploaded_image.url
