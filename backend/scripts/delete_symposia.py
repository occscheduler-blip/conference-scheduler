import sys                                                                                                                                          
from pathlib import Path  
from uuid import UUID                                                                                                                          
                                                                                                                                                    
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))                                                                                        
                
from dotenv import load_dotenv                                                                                                                      
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.supabase_io.delete import delete_symposium
from app.supabase_io.read import get_symposiums

for symposium in get_symposiums():
    print(symposium)
    print(symposium[1][0]["id"])
    print(type(symposium))
    delete_symposium(UUID(symposium[1][0]["id"]))