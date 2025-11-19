import pandas as pd
import numpy as np
import faiss
import pickle
import time
from pathlib import Path
from langchain_openai import OpenAIEmbeddings
import config

# Paths
THESES_EXCEL = "output/theses/theses_normalized.xlsx"
THESES_INDEX = "output/theses/faiss_index.bin"
EMBEDDING_MODEL = "text-embedding-3-small"


class ThesisEmbedder:
    def __init__(self, api_key):
        print("🔧 Initializing embedder...")
        self.embedding_client = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=api_key
        )
        self.index = None
        self.metadata_map = {}
        print("✅ Embedder ready.")

    def create_description(self, row):
        parts = []

        # Title (x3 weight)
        title = self._clean(row.get('عنوان پایان‌نامه') or row.get('عنوان'))
        if title:
            parts.extend([title, title, title])

        # Advisor (x3)
        advisor = self._clean(row.get('استاد راهنما'))
        if advisor:
            advisor_clean = advisor.replace('دکتر', '').replace('دكتر', '').strip()
            parts.extend([
                f"استاد راهنما {advisor_clean}",
                f"راهنما {advisor_clean}",
                advisor_clean
            ])

        # Co‑advisor (x2)
        co_advisor = self._clean(row.get('استاد مشاور'))
        if co_advisor:
            co_advisor_clean = co_advisor.replace('دکتر', '').replace('دكتر', '').strip()
            parts.extend([
                f"استاد مشاور {co_advisor_clean}",
                co_advisor_clean
            ])

        # Author (x2)
        author = self._clean(row.get('نویسنده') or row.get('پژوهشگر'))
        if author:
            parts.extend([f"نویسنده {author}", author])

        # Major (x2)
        field = self._clean(row.get('رشته') or row.get('رشته تحصیلی'))
        if field:
            parts.extend([f"رشته {field}", field])

        # Keywords (x2)
        keywords = self._clean(row.get('کلیدواژه‌ها') or row.get('توصیفگر'))
        if keywords:
            kw_list = keywords.replace('،', ',').split(',')
            for kw in kw_list[:5]:  # حداکثر 5 کلیدواژه
                kw = kw.strip()
                if kw:
                    parts.extend([kw, kw])

        # Degree (x1)
        degree = self._clean(row.get('مقطع'))
        if degree:
            parts.append(f"مقطع {degree}")

        # Faculty (x1)
        faculty = self._clean(row.get('دانشکده'))
        if faculty:
            parts.append(f"دانشکده {faculty}")

        # Year (x1)
        year = self._clean(row.get('سال') or row.get('سال دفاع'))
        if year:
            parts.append(f"سال {year}")

        description = " ".join(parts)
        description = ' '.join(description.split())

        return description if description else "No description"

    def _clean(self, value):
        if pd.isna(value) or value is None:
            return None
        value_str = str(value).strip()
        if value_str.lower() in ['nan', 'none', '', 'null']:
            return None
        return value_str

    def prepare_data(self, excel_path):
        print(f"📖 Loading Excel file: {excel_path}")

        try:
            df = pd.read_excel(excel_path, engine='openpyxl')
            print(f"✅ Loaded {len(df)} theses")
        except Exception as e:
            print(f"❌ Error loading file: {e}")
            return None

        df.columns = [col.strip() for col in df.columns]

        print("🔄 Building descriptions...")
        df['description'] = df.apply(self.create_description, axis=1)

        records = []
        for idx, row in df.iterrows():
            if 'رديف' in row or 'ردیف' in row:
                record_id = int(row.get('رديف') or row.get('ردیف') or idx)
            else:
                record_id = idx

            record = {
                'id': record_id,
                'text': row['description'],
                'metadata': {
                    'رديف': record_id,
                    'عنوان پایان‌نامه': self._clean(row.get('عنوان پایان‌نامه') or row.get('عنوان')) or '',
                    'نویسنده': self._clean(row.get('نویسنده')) or '',
                    'استاد راهنما': self._clean(row.get('استاد راهنما')) or '',
                    'استاد مشاور': self._clean(row.get('استاد مشاور')) or '',
                    'رشته': self._clean(row.get('رشته') or row.get('رشته تحصیلی')) or '',
                    'مقطع': self._clean(row.get('مقطع')) or '',
                    'سال': self._clean(row.get('سال') or row.get('سال دفاع')) or '',
                }
            }
            records.append(record)

        print(f"✅ Prepared {len(records)} records")
        return records

    def create_embeddings(self, records, batch_size=200):
        print("🔄 Generating embeddings...")
        print("⏳ This may take a few minutes...")

        texts = [r['text'] for r in records]
        total_texts = len(texts)
        all_vectors = []

        try:
            for i in range(0, total_texts, batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_texts + batch_size - 1) // batch_size

                print(f"🌐 Batch {batch_num}/{total_batches} ({len(batch_texts)} texts)...")

                batch_vectors = self.embedding_client.embed_documents(batch_texts)
                all_vectors.extend(batch_vectors)

                processed = min(i + batch_size, total_texts)
                progress = (processed / total_texts) * 100
                print(f"   ✅ {processed}/{total_texts} ({progress:.1f}%)")

                if i + batch_size < total_texts:
                    time.sleep(0.2)

            vectors_array = np.array(all_vectors, dtype='float32')
            print(f"\n✅ Generated {len(all_vectors)} embeddings")
            print(f"📊 Vector dimensions: {vectors_array.shape}")
            return vectors_array

        except Exception as e:
            print(f"\n❌ Error: {e}")
            return None

    def build_faiss_index(self, vectors, records):
        print("🔄 Building FAISS index...")

        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index = faiss.IndexIDMap(index)

        ids = np.array([r['id'] for r in records], dtype='int64')
        index.add_with_ids(vectors, ids)

        self.metadata_map = {r['id']: r['metadata'] for r in records}

        print("✅ FAISS index built")
        print(f"📊 Total vectors: {index.ntotal}")

        self.index = index
        return index

    def save_index(self, index_path):
        print(f"💾 Saving index: {index_path}")

        Path(index_path).parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, index_path)

        metadata_path = index_path.replace('.bin', '_metadata.pkl')
        with open(metadata_path, 'wb') as f:
            pickle.dump(self.metadata_map, f)

        print(f"✅ Saved:")
        print(f"   📁 {index_path}")
        print(f"   📁 {metadata_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Thesis Embedding - FIXED VERSION")
    print("=" * 60)

    try:
        embedder = ThesisEmbedder(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)

    records = embedder.prepare_data(THESES_EXCEL)
    if records is None:
        print("❌ Data preparation failed")
        exit(1)

    vectors = embedder.create_embeddings(records)
    if vectors is None:
        print("❌ Embedding generation failed")
        exit(1)

    embedder.build_faiss_index(vectors, records)

    embedder.save_index(THESES_INDEX)

    print("\n" + "=" * 60)
    print("✅ Done!")
    print("=" * 60)
