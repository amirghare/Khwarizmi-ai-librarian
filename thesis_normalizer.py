import pandas as pd
import re
from typing import Optional


class ThesisNormalizer:

    def __init__(self):
        pass

    def clean_text(self, text: str) -> str:
        if pd.isna(text) or text is None:
            return ""

        text = str(text).strip()

        # Remove extra spacing
        text = re.sub(r'\s+', ' ', text)

        # Remove special characters
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

        return text.strip()

    def extract_year(self, date_text: str) -> Optional[str]:
        if pd.isna(date_text):
            return None

        date_text = str(date_text).strip()

        match = re.search(r'(\d{4})', date_text)
        if match:
            year = match.group(1)
            if 1300 <= int(year) <= 1420:
                return year

        return None

    def normalize_professor_name(self, name: str) -> str:
        if pd.isna(name) or name is None:
            return ""

        name = str(name).strip()

        name = name.replace('/', '').strip()

        name = re.sub(r'\s+', ' ', name)

        return name.strip()

    def clean_keywords(self, keywords: str) -> str:
        if pd.isna(keywords):
            return ""

        keywords = str(keywords).strip()

        keywords = keywords.replace('،', '،').replace(';', '،').replace('-', '،')

        keywords = self.clean_text(keywords)

        return keywords

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:

        print("\n🧹 Starting data cleaning...")
        print("=" * 70)

        df_clean = df.copy()

        column_mapping = {
            'عنوان': 'عنوان پایان‌نامه',
            'پژوهشگر': 'نویسنده',
            'مقطع': 'مقطع',
            'رشته تحصيلي': 'رشته',
            'استاد راهنما': 'استاد راهنما',
            'استاد مشاور': 'استاد مشاور',
            'توصيفگر': 'کلیدواژه‌ها',
            'تاريخ دفاع': 'تاریخ دفاع',
            'رديف': 'رديف'
        }

        df_clean = df_clean.rename(columns=column_mapping)

        print("🔹 Cleaning title...")
        if 'عنوان پایان‌نامه' in df_clean.columns:
            df_clean['عنوان پایان‌نامه'] = df_clean['عنوان پایان‌نامه'].apply(self.clean_text)

        print("🔹 Cleaning author...")
        if 'نویسنده' in df_clean.columns:
            df_clean['نویسنده'] = df_clean['نویسنده'].apply(self.clean_text)

        print("🔹 Cleaning degree...")
        if 'مقطع' in df_clean.columns:
            df_clean['مقطع'] = df_clean['مقطع'].apply(self.clean_text)

        print("🔹 Cleaning major...")
        if 'رشته' in df_clean.columns:
            df_clean['رشته'] = df_clean['رشته'].apply(self.clean_text)

        print("🔹 Normalizing advisor name...")
        if 'استاد راهنما' in df_clean.columns:
            df_clean['استاد راهنما'] = df_clean['استاد راهنما'].apply(self.normalize_professor_name)

        print("🔹 Normalizing co-advisor name...")
        if 'استاد مشاور' in df_clean.columns:
            df_clean['استاد مشاور'] = df_clean['استاد مشاور'].apply(self.normalize_professor_name)

        print("🔹 Cleaning keywords...")
        if 'کلیدواژه‌ها' in df_clean.columns:
            df_clean['کلیدواژه‌ها'] = df_clean['کلیدواژه‌ها'].apply(self.clean_keywords)

        print("🔹 Extracting year...")
        if 'تاریخ دفاع' in df_clean.columns:
            df_clean['سال دفاع'] = df_clean['تاریخ دفاع'].apply(self.extract_year)

        if 'دانشکده' not in df_clean.columns:
            df_clean['دانشکده'] = ""

        print("🔹 Removing empty title rows...")
        initial_count = len(df_clean)
        df_clean = df_clean[df_clean['عنوان پایان‌نامه'].str.strip() != ""]
        removed_count = initial_count - len(df_clean)
        print(f" ✅ Removed {removed_count} empty rows")

        print("🔹 Creating combined search text...")
        df_clean['متن_جستجو'] = df_clean.apply(self._create_search_text, axis=1)

        columns_order = [
            'رديف',
            'عنوان پایان‌نامه',
            'نویسنده',
            'مقطع',
            'رشته',
            'استاد راهنما',
            'استاد مشاور',
            'دانشکده',
            'سال دفاع',
            'کلیدواژه‌ها',
            'تاریخ دفاع',
            'متن_جستجو'
        ]

        existing_columns = [col for col in columns_order if col in df_clean.columns]
        df_clean = df_clean[existing_columns]

        print("=" * 70)
        print(f"✅ Normalization complete: {len(df_clean)} theses")

        return df_clean

    def _create_search_text(self, row) -> str:
        parts = []

        if pd.notna(row.get('عنوان پایان‌نامه')):
            parts.append(str(row['عنوان پایان‌نامه']))

        if pd.notna(row.get('نویسنده')):
            parts.append(f"نویسنده: {row['نویسنده']}")

        if pd.notna(row.get('استاد راهنما')):
            parts.append(f"راهنما: {row['استاد راهنما']}")

        if pd.notna(row.get('استاد مشاور')):
            parts.append(f"مشاور: {row['استاد مشاور']}")

        if pd.notna(row.get('رشته')):
            parts.append(f"رشته: {row['رشته']}")

        if pd.notna(row.get('مقطع')):
            parts.append(f"مقطع: {row['مقطع']}")

        if pd.notna(row.get('دانشکده')):
            parts.append(f"دانشکده: {row['دانشکده']}")

        if pd.notna(row.get('سال دفاع')):
            parts.append(f"سال: {row['سال دفاع']}")

        if pd.notna(row.get('کلیدواژه‌ها')):
            parts.append(f"کلیدواژه: {row['کلیدواژه‌ها']}")

        return " | ".join(parts)


if __name__ == "__main__":

    print("=" * 70)
    print("🔄 Thesis Normalizer Test")
    print("=" * 70)

    sample_data = {
        'عنوان': ['بررسی الگوریتم‌های یادگیری ماشین', 'مطالعه شبکه‌های عصبی'],
        'پژوهشگر': ['علی احمدی', 'زهرا محمدی'],
        'مقطع': ['کارشناسی ارشد', 'دکتری'],
        'رشته تحصيلي': ['علوم کامپیوتر', 'هوش مصنوعی'],
        'استاد راهنما': ['/ دکتر رضایی', '/ دکتر کریمی'],
        'استاد مشاور': ['/ دکتر نوری', ''],
        'توصيفگر': ['یادگیری ماشین - الگوریتم', 'شبکه عصبی - deep learning'],
        'تاريخ دفاع': ['1402/05/15', '1401/09/20'],
        'رديف': [1, 2]
    }

    df = pd.DataFrame(sample_data)

    print("\n📊 Data:")
    print(df)

    normalizer = ThesisNormalizer()
    df_normalized = normalizer.normalize(df)

    print("\n✨ Normalized data:")
    print(df_normalized[['عنوان پایان‌نامه', 'نویسنده', 'سال دفاع', 'استاد راهنما']])

    print("\n✅ Test complete!")
