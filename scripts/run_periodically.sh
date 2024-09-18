#!/bin/bash

# Check if the interval parameter is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <interval_in_seconds>"
    exit 1
fi

INTERVAL=$1

while true; do
    python -m src.auto_archiver --config vi-config.yaml  --gsheet_feeder.sheet_id "1_87zjkMPWrbeM1pLFBhErqxFnGn2kJjMoSfBrpko_7c" --gdrive_storage.root_folder_id "1ekMiHv15Zg85lRNESD014dGWym-zAq-4" --project_name.value "vi_workflow_tests"
    
    # Sleep for the specified interval
    sleep $INTERVAL
done

# gcloud compute ssh --zone "us-central1-c" "vi-workflow-vm" --project "nytint-stg"
# gcloud compute scp --zone "us-central1-c" --recurse auto-archiver/ vi-workflow-vm:~/
