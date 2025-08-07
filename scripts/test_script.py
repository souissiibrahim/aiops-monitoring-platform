import pandas as pd

# Load the CSV
df = pd.read_csv("scripts/incident_type_training_data_large.csv")

# Normalize column names (strip spaces and lowercase)
df.columns = df.columns.str.strip().str.lower()

# Print column names for confirmation
print("📌 Columns found in CSV:", df.columns.tolist())

# Check for incident type label distribution
if 'incident_type_name' in df.columns:
    print("\n📊 Incident type distribution:\n")
    print(df['incident_type_name'].value_counts())
else:
    print("❌ Column 'incident_type_name' not found in CSV. Please check the header row.")
