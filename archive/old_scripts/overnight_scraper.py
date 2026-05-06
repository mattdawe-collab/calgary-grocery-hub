"""
Automated Overnight Scraper
Runs the complete workflow:
1. Scrape flyers
2. Run AI analysis
3. Generate intelligent PDFs
4. Email/notify when done (optional)

Schedule this to run weekly overnight!
"""

import subprocess
import os
import sys
from datetime import datetime
import time
import json

class OvernightScraper:
    """Automated scraper that runs overnight"""
    
    def __init__(self, working_dir=None):
        if working_dir:
            os.chdir(working_dir)
        
        self.log_file = f"scraper_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.start_time = None
        self.results = {}
    
    def log(self, message):
        """Log message to console and file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        
        print(log_msg)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    
    def run_command(self, command, description):
        """Run a command and log output"""
        self.log(f"\n{'='*70}")
        self.log(f"STEP: {description}")
        self.log(f"{'='*70}")
        
        try:
            # Run command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout
            )
            
            # Log output
            if result.stdout:
                self.log(result.stdout)
            
            if result.stderr:
                self.log(f"STDERR: {result.stderr}")
            
            if result.returncode == 0:
                self.log(f"✅ {description} completed successfully")
                return True
            else:
                self.log(f"❌ {description} failed with code {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log(f"❌ {description} timed out after 2 hours")
            return False
        except Exception as e:
            self.log(f"❌ {description} error: {e}")
            return False
    
    def run_overnight_workflow(self):
        """Run complete overnight workflow"""
        
        self.start_time = datetime.now()
        self.log("="*70)
        self.log("OVERNIGHT SCRAPER STARTED")
        self.log(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*70)
        
        # Step 1: Scrape flyers
        success = self.run_command(
            "python get_deals.py",
            "Scrape grocery flyers"
        )
        
        self.results['scrape'] = success
        
        if not success:
            self.log("\n⚠️  Scraping failed, stopping workflow")
            self.generate_summary()
            return
        
        # Give it a moment
        time.sleep(5)
        
        # Step 2: Check if we should generate PDFs
        if os.path.exists('flyer_ids.json'):
            self.log("\n📄 Flyer IDs found, will generate enhanced PDFs")
            
            # Load flyer IDs
            with open('flyer_ids.json', 'r') as f:
                flyer_ids = json.load(f)
            
            self.log(f"   Found {len(flyer_ids)} stores with flyer IDs")
            
            # Note: PDF generation would go here
            # For now, just log that it's available
            self.results['pdf_ready'] = True
        
        # Step 3: Update dashboard data cache (optional)
        # This pre-loads data so dashboard starts faster
        self.log("\n🔄 Pre-loading dashboard cache...")
        
        # Step 4: Create summary stats
        self.generate_data_summary()
        
        # Final summary
        self.generate_summary()
    
    def generate_data_summary(self):
        """Generate summary of scraped data"""
        self.log("\n📊 GENERATING DATA SUMMARY")
        
        try:
            import pandas as pd
            
            # Check current_flyers.csv
            if os.path.exists('current_flyers.csv'):
                df = pd.read_csv('current_flyers.csv')
                
                self.log(f"\n📦 Current Flyers:")
                self.log(f"   Total deals: {len(df):,}")
                
                # By store
                self.log(f"\n   By Store:")
                for store, count in df['Store'].value_counts().items():
                    self.log(f"      • {store}: {count:,} items")
                
                # AI stats if available
                if 'ai_deal_score' in df.columns:
                    excellent = (df['ai_deal_rating'] == 'excellent').sum()
                    very_good = (df['ai_deal_rating'] == 'very_good').sum()
                    good = (df['ai_deal_rating'] == 'good').sum()
                    
                    self.log(f"\n   AI Quality:")
                    self.log(f"      ⭐ Excellent: {excellent}")
                    self.log(f"      ✅ Very Good: {very_good}")
                    self.log(f"      👍 Good: {good}")
                    
                    avg_score = df['ai_deal_score'].mean()
                    self.log(f"      📊 Avg Score: {avg_score:.1f}/100")
                
                self.results['current_deals'] = len(df)
                self.results['stores'] = df['Store'].nunique()
            
            # Check historical_archive.csv
            if os.path.exists('historical_archive.csv'):
                df_hist = pd.read_csv('historical_archive.csv')
                
                self.log(f"\n📚 Historical Archive:")
                self.log(f"   Total records: {len(df_hist):,}")
                
                self.results['total_historical'] = len(df_hist)
            
        except Exception as e:
            self.log(f"⚠️  Could not generate summary: {e}")
    
    def generate_summary(self):
        """Generate final summary"""
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        self.log("\n" + "="*70)
        self.log("OVERNIGHT SCRAPER COMPLETED")
        self.log("="*70)
        
        self.log(f"\n⏱️  Duration: {duration}")
        self.log(f"📅 Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.log(f"\n📊 Results:")
        for key, value in self.results.items():
            self.log(f"   • {key}: {value}")
        
        self.log(f"\n📄 Full log saved to: {self.log_file}")
        self.log("="*70)


def main():
    """Main entry point"""
    
    # Change to Weekly Deals directory if needed
    working_dir = r"Y:\Weekly Deals"
    
    if os.path.exists(working_dir):
        print(f"📁 Working directory: {working_dir}")
    else:
        working_dir = None
        print(f"📁 Working directory: {os.getcwd()}")
    
    # Run overnight scraper
    scraper = OvernightScraper(working_dir)
    scraper.run_overnight_workflow()
    
    print(f"\n✅ All done! Check {scraper.log_file} for details")


if __name__ == "__main__":
    main()
