import pandas as pd
import re


INPUT_FILE = "data/books.xlsx"
OUTPUT_FILE = "output/final_normalize.xlsx"

print("=" * 70)
print("🔄 Starting complete library file normalization")
print("=" * 70)


def arabic_to_persian(text):
    """Convert Arabic letters to Persian"""
    if pd.isna(text):
        return text

    text = str(text)

    # Convert Arabic letters
    replacements = {
        'ي': 'ی',
        'ك': 'ک',
        'ؤ': 'و',
        'إ': 'ا',
        'أ': 'ا',
        'ٱ': 'ا',
        'ة': 'ه',
        'ۀ': 'ه',
    }

    for arabic, persian in replacements.items():
        text = text.replace(arabic, persian)

    return text

def clean_author(author):
    if pd.isna(author) or not author:
        return ""

    author = str(author).strip()

    # Convert Arabic to Persian
    author = arabic_to_persian(author)

    # Remove leading /
    author = author.lstrip('/')

    # Remove trailing .
    author = author.rstrip('.')

    # Remove extra spaces
    author = re.sub(r'\s+', ' ', author)

    return author.strip()


def clean_subject(subject):
    if pd.isna(subject) or not subject:
        return ""

    subject = str(subject).strip()

    # Convert Arabic to Persian
    subject = arabic_to_persian(subject)

    # Replace signs(below line) with comma
    # ◄ and -- and ; to ,
    subject = subject.replace('◄', '،')
    subject = subject.replace('--', '،')
    subject = subject.replace(';', '،')
    subject = subject.replace(' - ', '،')

    # Remove extra spaces
    subject = re.sub(r'\s+', ' ', subject)

    # Clean commas (space after comma, remove duplicate commas)
    subject = re.sub(r'،\s*،+', '،', subject)
    subject = re.sub(r'،\s*', '، ', subject) # One space after comma
    subject = subject.strip('،').strip()  # Remove comma from start and end

    return subject


def clean_title(title):
    if pd.isna(title) or not title:
        return ""

    title = str(title).strip()

    # Convert Arabic to Persian
    title = arabic_to_persian(title)

    # Remove extra spaces
    title = re.sub(r'\s+', ' ', title)

    return title.strip()


def clean_publisher(publisher):
    if pd.isna(publisher) or not publisher:
        return ""

    publisher = str(publisher).strip()

    # Convert Arabic to Persian
    publisher = arabic_to_persian(publisher)

    # Remove extra spaces
    publisher = re.sub(r'\s+', ' ', publisher)

    return publisher.strip()


def clean_cutter(cutter):
    if pd.isna(cutter) or not cutter:
        return ""

    cutter = str(cutter).strip()

    # Remove trailing /
    if cutter.endswith('/'):
        cutter = cutter[:-1]

    return cutter


def clean_location(location):
    if pd.isna(location) or not location:
        return ""

    location = str(location).strip()

    # Convert Arabic to Persian
    location = arabic_to_persian(location)

    return location.strip()


def clean_general(text):
    if pd.isna(text) or not text:
        return ""

    text = str(text).strip()

    # Convert Arabic to Persian
    text = arabic_to_persian(text)

    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()

# Load and process
print(f"📖 Reading file: {INPUT_FILE}")
df = pd.read_excel(INPUT_FILE)

print(f"✅ File read: {len(df)} rows, {len(df.columns)} columns")
print(f"\n📋 Existing columns:")
for i, col in enumerate(df.columns, 1):
    print(f"   {i:2d}. {col}")

# Normalize column names
df.columns = [col.strip() for col in df.columns]

print("\n" + "=" * 70)
print("🧹 Starting data cleanup...")
print("=" * 70)

# Clean title
print("🔹 Cleaning title...")
df['عنوان'] = df['عنوان'].apply(clean_title)

# Clean author
print("🔹 Cleaning author...")
df['پديدآورنده'] = df['پديدآورنده'].apply(clean_author)

# # Clean subject
print("🔹 Cleaning subject...")
df['موضوع'] = df['موضوع'].apply(clean_subject)

# Clean publisher
print("🔹 Cleaning publisher...")
df['ناشر'] = df['ناشر'].apply(clean_publisher)

# Clean cutter
print("🔹 Cleaning cutter...")
if 'كاتر' in df.columns:
    df['كاتر'] = df['كاتر'].apply(clean_cutter)
elif 'کاتر' in df.columns:
    df['کاتر'] = df['کاتر'].apply(clean_cutter)

# Clean storage location
print("🔹 Cleaning storage location...")
if 'محل نگهداري' in df.columns:
    df['محل نگهداري'] = df['محل نگهداري'].apply(clean_location)
elif 'محل نگهداری' in df.columns:
    df['محل نگهداری'] = df['محل نگهداری'].apply(clean_location)

# General cleanup for other fields
print("🔹 Cleaning other fields...")
other_fields = ['عناوين ديگر', 'شرح پديدآور', 'محل نشر', 'فروست',
                'يادداشت', 'رده اصلي', 'شماره رده']

for field in other_fields:
    if field in df.columns:
        df[field] = df[field].apply(clean_general)

# Remove empty rows (without title)
print("🔹 Removing empty rows...")
initial_count = len(df)
df = df[df['عنوان'].str.len() > 0]
removed_count = initial_count - len(df)
print(f"   ✅ {removed_count} empty rows removed")

# Create combined_text for embedding
print("🔹 Creating combined text...")


def create_combined_text(row):
    parts = []

    if row['عنوان']:
        parts.append(f"عنوان: {row['عنوان']}")

    if row['پديدآورنده']:
        parts.append(f"نویسنده: {row['پديدآورنده']}")

    if row['موضوع']:
        parts.append(f"موضوع: {row['موضوع']}")

    if row['ناشر']:
        parts.append(f"ناشر: {row['ناشر']}")

    return " | ".join(parts)

df['combined_text'] = df.apply(create_combined_text, axis=1)


# Save File
print("\n" + "=" * 70)
print(f"💾 Saving: {OUTPUT_FILE}")
df.to_excel(OUTPUT_FILE, index=False)

print(f"✅ Normalized file saved!")
print(f"   📊 Number of rows: {len(df)}")
print(f"   📋 Number of columns: {len(df.columns)}")

# Show sample
print("\n" + "=" * 70)
print("📖 Sample data (first row):")
print("=" * 70)

first_row = df.iloc[0]
important_fields = [
    'رديف', 'عنوان', 'پديدآورنده', 'موضوع', 'ناشر',
    'تاريخ نشر', 'رده اصلي', 'شماره رده', 'كاتر', 'محل نگهداري'
]

for field in important_fields:
    if field in df.columns:
        value = first_row[field]
        if len(str(value)) > 60:
            value = str(value)[:60] + "..."
        print(f"{field:20s}: {value}")

print("\n" + "=" * 70)
print("✅ Sample changes:")
print("=" * 70)

# Show a few samples before/after
if len(df) > 0:
    print("\n🔹 نمونه نویسنده:")
    sample_authors = df['پديدآورنده'].dropna().head(3)
    for i, author in enumerate(sample_authors, 1):
        print(f"   {i}. {author}")

    print("\n🔹 نمونه موضوع:")
    sample_subjects = df['موضوع'].dropna().head(3)
    for i, subject in enumerate(sample_subjects, 1):
        if len(subject) > 80:
            subject = subject[:80] + "..."
        print(f"   {i}. {subject}")

print("\n" + "=" * 70)
print("✅ Done! Now you can use this file.")
print("=" * 70)
