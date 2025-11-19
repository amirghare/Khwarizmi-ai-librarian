import pandas as pd
import numpy as np
import faiss
import pickle
import time
from pathlib import Path
from langchain_openai import OpenAIEmbeddings


OPENAI_API_KEY="YOUR_OPENAI_API_KEY_HERE"
NORMALIZED_EXCEL = "output/normalized_books.xlsx"
FAISS_INDEX_PATH = "output/faiss_index.bin"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
TOP_K_RESULTS = 5

# Columns to embed
COLUMNS_TO_EMBED = [
    "عنوان",
    "موضوع",
    "پديدآورنده",
    "رده اصلي",
]


# Main Embedder class
class BookEmbedder:
    def __init__(self, api_key=None):
        print("🔧 Initializing Embedder...")

        if api_key is None:
            api_key = OPENAI_API_KEY

        if api_key == "Place for API key":
            raise ValueError("❌ Please enter OpenAI API Key in book_embedder.py or config.py")

        # Create embedding client
        self.embedding_client = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=api_key
        )

        # FAISS index
        self.index = None
        self.metadata_map = {}  # Mapping ID to metadata

        print("✅ Embedder is ready")


    def create_description(self, row):
        parts = []

        # Title (weight 3x) - very important!
        if 'عنوان' in row and pd.notna(row['عنوان']) and str(row['عنوان']).strip():
            title = str(row['عنوان']).strip()
            # Repeat for increased weight
            parts.extend([title, title, title])

        # Author (weight 3x) - very important!
        if 'پديدآورنده' in row and pd.notna(row['پديدآورنده']) and str(row['پديدآورنده']).strip():
            author = str(row['پديدآورنده']).strip()
            # Clean author
            author = author.replace('/', ' ').replace('.', ' ').replace('،', ' ')
            author = ' '.join(author.split())  # Remove extra spaces
            if author and author not in ['nan', 'none', '']:
                parts.extend([f"نویسنده {author}", f"اثر {author}", author])

        # Subject (weight 2x) - important
        if 'موضوع' in row and pd.notna(row['موضوع']) and str(row['موضوع']).strip():
            subject = str(row['موضوع']).strip()
            # Clean subject
            subject = subject.replace('،', ' ')
            subject = ' '.join(subject.split())
            if subject and subject not in ['nan', 'none', '']:
                parts.extend([f"موضوع {subject}", subject])

        # Main category (weight 1x) - less important
        if 'رده اصلي' in row and pd.notna(row['رده اصلي']) and str(row['رده اصلي']).strip():
            category = str(row['رده اصلي']).strip()
            if category and category not in ['nan', 'none', '']:
                parts.append(category)

        # Other titles (weight 1x) - if exists
        if 'عناوين ديگر' in row and pd.notna(row['عناوين ديگر']) and str(row['عناوين ديگر']).strip():
            alt_title = str(row['عناوين ديگر']).strip()
            if alt_title and alt_title not in ['nan', 'none', '']:
                parts.append(alt_title)

        # Combine with spaces
        description = " ".join(parts)

        # Final cleanup
        description = ' '.join(description.split())  # Remove extra spaces

        return description if description else "No description"

    def prepare_data(self, excel_path):
        print(f"📖 Reading file: {excel_path}")

        try:
            df = pd.read_excel(excel_path, engine='openpyxl')
            print(f"✅ File read successfully. Number of records: {len(df)}")
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return None

        # Create descriptions for each book
        print("🔄 Creating book descriptions...")
        df['description'] = df.apply(self.create_description, axis=1)

        # Convert to list of dictionaries
        records = []
        for idx, row in df.iterrows():
            # Extract ID
            if 'رديف' in row:
                record_id = int(row['رديف']) if pd.notna(row['رديف']) else idx
            else:
                record_id = idx

            record = {
                'id': record_id,
                'text': row['description'],
                'metadata': {
                    'رديف': record_id,
                    'عنوان': str(row.get('عنوان', '')) if pd.notna(row.get('عنوان')) else '',
                    'پديدآورنده': str(row.get('پديدآورنده', '')) if pd.notna(row.get('پديدآورنده')) else '',
                    'رده اصلي': str(row.get('رده اصلي', '')) if pd.notna(row.get('رده اصلي')) else '',
                    'موضوع': str(row.get('موضوع', '')) if pd.notna(row.get('موضوع')) else '',
                    'ناشر': str(row.get('ناشر', '')) if pd.notna(row.get('ناشر')) else '',
                    'تاريخ نشر': str(row.get('تاريخ نشر', '')) if pd.notna(row.get('تاريخ نشر')) else '',
                    'محل نشر': str(row.get('محل نشر', '')) if pd.notna(row.get('محل نشر')) else ''
                }
            }
            records.append(record)

        print(f"✅ {len(records)} records ready")
        return records

    def create_embeddings(self, records, batch_size=200):
        print("🔄 Creating embeddings...")
        print("⏳ This step may take a few minutes...")

        # Extract texts
        texts = [r['text'] for r in records]
        total_texts = len(texts)

        # Create embeddings in batches
        all_vectors = []

        try:
            # Split into smaller batches
            for i in range(0, total_texts, batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_texts + batch_size - 1) // batch_size

                print(f"🌐 Processing batch {batch_num}/{total_batches} ({len(batch_texts)} texts)...")

                # Send batch to OpenAI
                batch_vectors = self.embedding_client.embed_documents(batch_texts)
                all_vectors.extend(batch_vectors)

                # Show progress
                processed = min(i + batch_size, total_texts)
                progress = (processed / total_texts) * 100
                print(f"   ✅ {processed}/{total_texts} texts processed ({progress:.1f}%)")

                # Wait a bit to avoid rate limit
                if i + batch_size < total_texts:
                    time.sleep(0.2)  # 0.2 second wait (faster)

            vectors_array = np.array(all_vectors, dtype='float32')

            print(f"\n✅ {len(all_vectors)} embeddings created successfully")
            print(f"📊 Dimensions per vector: {vectors_array.shape[1]}")

            return vectors_array

        except Exception as e:
            print(f"\n❌ Error creating embeddings: {e}")
            print(f"💡 Number of successful embeddings before error: {len(all_vectors)}")
            return None

    def build_faiss_index(self, vectors, records):
        print("🔄 Building FAISS index...")

        # Create index
        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index = faiss.IndexIDMap(index)

        # Array of IDs
        ids = np.array([r['id'] for r in records], dtype='int64')

        # Add vectors to index
        index.add_with_ids(vectors, ids)

        # Save metadata mapping
        self.metadata_map = {r['id']: r['metadata'] for r in records}

        print(f"✅ FAISS index built successfully")
        print(f"📊 Number of vectors in index: {index.ntotal}")

        self.index = index
        return index

    def save_index(self, index_path):
        print(f"💾 Saving index: {index_path}")

        # Create directory
        Path(index_path).parent.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        faiss.write_index(self.index, index_path)

        # Save metadata
        metadata_path = index_path.replace('.bin', '_metadata.pkl')
        with open(metadata_path, 'wb') as f:
            pickle.dump(self.metadata_map, f)

        print(f"✅ Index and metadata saved")
        print(f"📁 Index file: {index_path}")
        print(f"📁 Metadata file: {metadata_path}")

    def load_index(self, index_path):
        print(f"📖 Loading index: {index_path}")

        # Load FAISS index
        self.index = faiss.read_index(index_path)

        # Load metadata
        metadata_path = index_path.replace('.bin', '_metadata.pkl')
        with open(metadata_path, 'rb') as f:
            self.metadata_map = pickle.load(f)

        print(f"✅ Index loaded. Number of vectors: {self.index.ntotal}")

    def embed_query(self, query):
        try:
            vector = self.embedding_client.embed_query(query)
            return np.array([vector], dtype='float32')
        except Exception as e:
            print(f"❌ Error embedding query: {e}")
            return None

    def search(self, query, k=None):
        if k is None:
            k = TOP_K_RESULTS

        # embedding query
        query_vector = self.embed_query(query)

        if query_vector is None:
            return []

        # Search in FAISS
        distances, indices = self.index.search(query_vector, k)

        # Extract metadata
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx != -1 and int(idx) in self.metadata_map:
                result = self.metadata_map[int(idx)].copy()
                result['distance'] = float(dist)
                results.append(result)

        return results



if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Phase 2: Embedding and FAISS index")
    print("=" * 60)

    # Create embedder
    try:
        embedder = BookEmbedder()
    except ValueError as e:
        print(e)
        exit(1)

    # Prepare data
    records = embedder.prepare_data(NORMALIZED_EXCEL)

    if records is None:
        print("❌ Error in data preparation")
        exit(1)

    # Create embeddings
    vectors = embedder.create_embeddings(records)

    if vectors is None:
        print("❌ Error creating embeddings")
        exit(1)

    # Build index
    embedder.build_faiss_index(vectors, records)

    # Save index
    embedder.save_index(FAISS_INDEX_PATH)

    print("\n" + "=" * 60)
    print("✅ Embedding and indexing process completed successfully!")
    print("=" * 60)

    # Test search
    print("\n🔍 Search test:")
    test_queries = [
        "کتاب های صادق هدایت",
        "داستان کوتاه فارسی",
        "شعر فارسی"
    ]

    for test_query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"Query: «{test_query}»")
        results = embedder.search(test_query, k=3)

        if results:
            print(f"📚 {len(results)} results found:")
            for i, r in enumerate(results, 1):
                print(f"\n{i}. [ردیف {r['رديف']}] {r['عنوان']}")
                if r['پديدآورنده']:
                    print(f"   نویسنده: {r['پديدآورنده']}")
                if r['موضوع']:
                    print(f"   موضوع: {r['موضوع']}")
                print(f"   فاصله: {r['distance']:.2f}")
        else:
            print("❌ No results found")
