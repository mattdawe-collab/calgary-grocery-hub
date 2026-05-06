"""
Setup Windows Task Scheduler
Creates a scheduled task to run the scraper overnight every week
"""

import subprocess
import os
from datetime import datetime, timedelta

def create_scheduled_task():
    """Create Windows scheduled task"""
    
    print("=" * 70)
    print("WINDOWS TASK SCHEDULER SETUP")
    print("=" * 70)
    
    # Configuration
    task_name = "GroceryHubWeeklyScraper"
    script_path = os.path.join(os.getcwd(), "overnight_scraper.py")
    python_path = subprocess.check_output("where python", shell=True).decode().strip().split('\n')[0]
    
    print(f"\n📋 Task Configuration:")
    print(f"   Task Name: {task_name}")
    print(f"   Script: {script_path}")
    print(f"   Python: {python_path}")
    
    # When to run (default: Every Tuesday at 2:00 AM)
    print(f"\n⏰ Schedule:")
    print(f"   Every Tuesday at 2:00 AM")
    print(f"   (After stores update their flyers)")
    
    # Create XML for scheduled task
    working_dir = os.getcwd()
    
    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Calgary Grocery Hub - Weekly flyer scraper with AI analysis</Description>
    <Author>{os.getenv('USERNAME')}</Author>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2025-12-24T02:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <Tuesday />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{python_path}"</Command>
      <Arguments>"{script_path}"</Arguments>
      <WorkingDirectory>{working_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''
    
    # Save XML
    xml_file = "scheduled_task.xml"
    with open(xml_file, 'w', encoding='utf-16') as f:
        f.write(xml)
    
    print(f"\n✅ Created task XML: {xml_file}")
    
    # Instructions
    print("\n" + "=" * 70)
    print("SETUP INSTRUCTIONS")
    print("=" * 70)
    
    print(f"\n🎯 OPTION 1: Automatic (Run as Administrator)")
    print(f"   Run this command in PowerShell (as Admin):")
    print(f"   schtasks /create /tn \"{task_name}\" /xml \"{xml_file}\" /f")
    
    print(f"\n🎯 OPTION 2: Manual (Easier)")
    print(f"   1. Open Task Scheduler (taskschd.msc)")
    print(f"   2. Click 'Import Task...'")
    print(f"   3. Select: {xml_file}")
    print(f"   4. Adjust settings if needed")
    print(f"   5. Click OK")
    
    print(f"\n🎯 OPTION 3: Quick Setup")
    print(f"   1. Press Windows + R")
    print(f"   2. Type: taskschd.msc")
    print(f"   3. Create Basic Task → Name it '{task_name}'")
    print(f"   4. Trigger: Weekly, Tuesday, 2:00 AM")
    print(f"   5. Action: Start a Program")
    print(f"      Program: {python_path}")
    print(f"      Arguments: \"{script_path}\"")
    print(f"      Start in: {working_dir}")
    
    print("\n" + "=" * 70)
    print("TESTING")
    print("=" * 70)
    
    print(f"\n🧪 Test the scraper now:")
    print(f"   python overnight_scraper.py")
    
    print(f"\n🧪 Test scheduled task:")
    print(f"   schtasks /run /tn \"{task_name}\"")
    
    print("\n" + "=" * 70)
    
    # Try to create automatically
    response = input("\nCreate task now? (requires Admin) [y/N]: ")
    
    if response.lower() == 'y':
        try:
            cmd = f'schtasks /create /tn "{task_name}" /xml "{xml_file}" /f'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("\n✅ Task created successfully!")
                print(f"   Check Task Scheduler to verify")
            else:
                print(f"\n❌ Failed to create task")
                print(f"   Error: {result.stderr}")
                print(f"   Use manual setup instead")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print(f"   Use manual setup instead")


if __name__ == "__main__":
    create_scheduled_task()
