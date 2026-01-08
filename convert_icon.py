from PIL import Image

img = Image.open("icon.png")
# アイコン用にサイズ調整（必要な場合）
img.save("icon.ico", format='ICO', sizes=[(256, 256)])
print("Converted icon.png to icon.ico")
