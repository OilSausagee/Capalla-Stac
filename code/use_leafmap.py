import pystac
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt
import os

# ==== 參數 ====
STAC_CATALOG = r"D:\Capalla_data\stac\catalog.json"
# ============

print("1. 讀取 STAC...")
cat = pystac.read_file(STAC_CATALOG)
items = list(cat.get_all_items())

if not items:
    print("找不到 Items！")
    exit()

# 只畫前 3 張來檢查
print(f"2. 準備繪製前 3 張影像 (共 {len(items)} 張)...")

for i, item in enumerate(items[:3]):
    print(f"  - 正在讀取: {item.id}")
    
    if 'data' in item.assets:
        tif_path = item.assets['data'].get_absolute_href()
        
        if os.path.exists(tif_path):
            try:
                with rasterio.open(tif_path) as src:
                    # 設定畫布大小
                    plt.figure(figsize=(10, 10))
                    
                    # 使用 rasterio 的 show 來繪圖
                    # cmap='gray' 代表用灰階顯示 (SAR 影像通常是單波段灰階)
                    show(src, title=f"{item.id}\n{item.datetime}", cmap='gray')
                    
                    # 顯示出來 (會跳出視窗)
                    plt.show()
                    print("    ✅ 繪製成功")
            except Exception as e:
                print(f"    [錯誤] 無法讀取影像: {e}")
        else:
            print(f"    [警告] 找不到檔案: {tif_path}")

print("完成！")