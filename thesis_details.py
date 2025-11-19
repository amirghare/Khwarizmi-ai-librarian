import pandas as pd
from functools import lru_cache


class ThesisDetailsLoader:
    def __init__(self, excel_path):
        print(f"📄 Loading thesis details from: {excel_path}")
        self.df = pd.read_excel(excel_path)

        # Normalize column names
        self.df.columns = [col.strip() for col in self.df.columns]

        # Create fast index for access by row
        if 'ردیف' in self.df.columns:
            self.df.set_index('ردیف', inplace=True)
        elif 'رديف' in self.df.columns:
            self.df.set_index('رديف', inplace=True)

        print(f"✅ {len(self.df)} theses loaded")
        print(f"📋 Columns: {list(self.df.columns)[:10]}...")

    @lru_cache(maxsize=1000)
    def get_thesis_details(self, row_id):
        try:
            row_id = int(row_id)
            if row_id not in self.df.index:
                return None

            thesis = self.df.loc[row_id]

            return {
                'رديف': row_id,
                'عنوان': self._clean_value(thesis.get('عنوان', '')),
                'نویسنده': self._clean_value(thesis.get('نویسنده', '')),
                'مقطع': self._clean_value(thesis.get('مقطع', '')),
                'رشته تحصیلی': self._clean_value(thesis.get('رشته تحصیلی', '')),
                'استاد راهنما': self._clean_value(thesis.get('استاد راهنما', '')),
                'استاد مشاور': self._clean_value(thesis.get('استاد مشاور', '')),
                'تاریخ دفاع': self._clean_value(thesis.get('تاریخ دفاع', '')),
                'سال': self._clean_value(thesis.get('سال', '')),
                'شماره راهنما': self._clean_value(thesis.get('شماره راهنما', '')),
                'کلیدواژه': self._clean_value(thesis.get('کلیدواژه', '') or thesis.get('توصیفگر', '')),
            }
        except Exception as e:
            print(f"⚠️ Error getting thesis details {row_id}: {e}")
            return None

    def _clean_value(self, value):
        if pd.isna(value):
            return ""

        value = str(value).strip()

        if value.lower() in ['nan', 'none', '']:
            return ""

        return value

    def get_available_filters(self):
        filters = {}

        # Degree level
        if 'مقطع' in self.df.columns:
            degrees = self.df['مقطع'].dropna().unique().tolist()
            filters['مقطع'] = [d for d in degrees if d]

        # Year
        if 'سال' in self.df.columns:
            years = self.df['سال'].dropna().unique().tolist()
            filters['سال'] = sorted([y for y in years if y], reverse=True)

        # Field of study
        if 'رشته تحصیلی' in self.df.columns:
            fields = self.df['رشته تحصیلی'].value_counts().head(20).index.tolist()
            filters['رشته'] = fields

        # Supervisor
        if 'استاد راهنما' in self.df.columns:
            advisors = self.df['استاد راهنما'].value_counts().head(50).index.tolist()
            filters['استاد راهنما'] = [a for a in advisors if a]

        return filters

    def filter_results(self, results, filters):
        filtered = []

        for result in results:
            row_id = result.get('رديف')
            if not row_id or row_id not in self.df.index:
                continue

            thesis = self.df.loc[row_id]
            match = True

            # Check each filter
            for filter_key, filter_value in filters.items():
                if not filter_value:
                    continue

                if filter_key == 'مقطع':
                    if thesis.get('مقطع', '') != filter_value:
                        match = False
                        break

                elif filter_key == 'سال':
                    if str(filter_value) not in str(thesis.get('سال', '')):
                        match = False
                        break

                elif filter_key == 'رشته':
                    if filter_value not in str(thesis.get('رشته تحصیلی', '')):
                        match = False
                        break

                elif filter_key == 'استاد راهنما':
                    if filter_value not in str(thesis.get('استاد راهنما', '')):
                        match = False
                        break

            if match:
                filtered.append(result)

        return filtered
