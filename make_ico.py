from PIL import Image

img = Image.open("app_icon.png").convert("RGBA")
sizes = [(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)]
img.save("app_icon.ico", sizes=sizes)
print("OK -> app_icon.ico")
