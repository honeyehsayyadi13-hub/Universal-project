from supabase import create_client

# Replace these with your Supabase project information
url = "https://azbjjemtcpaeqfqauzod.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF6YmpqZW10Y3BhZXFmcWF1em9kIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0Mzc3NDIsImV4cCI6MjA5NjAxMzc0Mn0.VQ84Z1DDokGWDaW11y_n0rXRKFfN6T7pcC-h4PsAT34"

supabase = create_client(url, key)