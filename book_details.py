import pandas as pd
from functools import lru_cache


class BookDetailsLoader:
    def __init__(self, excel_path):
        print(f"📚 Loading book details from: {excel_path}")
        self.df = pd.read_excel(excel_path)

        # Normalize column names
        self.df.columns = [col.strip() for col in self.df.columns]

        # Create fast index for access by row number
        self.df.set_index('رديف', inplace=True)

        print(f"✅ {len(self.df)} books loaded")
        print(f"📋 Columns: {list(self.df.columns)[:10]}...")

    @lru_cache(maxsize=1000)
    def get_book_details(self, row_id):
        try:
            row_id = int(row_id)
            if row_id not in self.df.index:
                return None

            book = self.df.loc[row_id]

            # Build retrieval number
            retrieval_number = self._build_retrieval_number(book)

            # Get storage location
            location = self._get_location(book)

            return {
                'رديف': row_id,
                'عنوان': self._clean_value(book.get('عنوان', '')),
                'پديدآورنده': self._clean_value(book.get('پديدآورنده', '')),
                'ناشر': self._clean_value(book.get('ناشر', '')),
                'تاريخ نشر': self._clean_value(book.get('تاريخ نشر', '')),
                'موضوع': self._clean_value(book.get('موضوع', '')),
                'شماره_بازیابی': retrieval_number,
                'محل_نگهداری': location,
                'شابك': self._clean_value(book.get('شابك', '')),
                'تعداد صفحات': self._clean_value(book.get('تعداد صفحات', '')),
            }
        except Exception as e:
            print(f"⚠️ Error getting book details {row_id}: {e}")
            return None

    def _build_retrieval_number(self, book):
        parts = []

        main_class = self._clean_value(book.get('رده اصلي') or book.get('رده اصلی', ''))
        if main_class:
            parts.append(main_class)

        class_number = self._clean_value(book.get('شماره رده', ''))
        if class_number:
            parts.append(class_number)

        cutter = self._clean_value(book.get('كاتر') or book.get('کاتر', ''))
        if cutter and cutter.endswith('/'):
            cutter = cutter[:-1]
        if cutter:
            parts.append(cutter)

        if not parts:
            return "نامشخص"

        return " ".join(parts)

    def _get_location(self, book):
        location = self._clean_value(
            book.get('محل نگهداري') or
            book.get('محل نگهداری', '')
        )

        if not location:
            return "کتابخانه مرکزی"

        return location

    def _clean_value(self, value):
        if pd.isna(value):
            return ""

        value = str(value).strip()

        # If it's nan
        if value.lower() in ['nan', 'none', '']:
            return ""

        return value
