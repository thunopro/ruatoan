#!/usr/bin/env python3
"""For store product URLs (stdin), fetch page (cached) and print status + detected author/publisher."""
import sys, os, re, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F

def meta(u):
    m = F.fetch(u)
    t = F.text(u)
    au = re.search(r'(?:Tác giả|Tác Giả|TÁC GIẢ|Chủ biên)\s*:?\s*([^:|]{3,90}?)(?=\s+(?:Nhà xuất bản|NXB|Nhà phát hành|Số trang|Năm|Kích thước|Khổ|Hình thức|Ngôn ngữ|Mã|Dịch giả|Đơn vị|Công ty|Trọng lượng|Loại bìa|Nhà cung cấp|Phân phối|Cân nặng)|$|\.|,\s*Nhà)', t)
    pub = re.search(r'(?:Nhà xuất bản|NXB)\s*:?\s*([^:|]{3,50}?)(?=\s+(?:Năm|Số trang|Kích thước|Khổ|Hình thức|Tác giả|Ngôn ngữ|Trọng lượng|Nhà phát hành|Loại bìa)|$|\.)', t)
    au_ru = re.search(r'(?:Автор\(ы\)|Авторы?|Составител\w*)\s*:?\s*([^:|]{3,120}?)(?=\s+(?:Год|Издательство|Серия|ISBN|Страниц|Переплет|Формат|Тираж|Цена|Аннотация|Описание)|$)', t)
    return m['status'], u, (au.group(1).strip() if au else (au_ru.group(1).strip() if au_ru else '')), (pub.group(1).strip() if pub else ''), m.get('title', '')[:90]

if __name__ == '__main__':
    urls = [l.strip() for l in sys.stdin if l.strip() and not l.startswith('#')]
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(meta, urls):
            print(' | '.join(str(x) for x in r))
