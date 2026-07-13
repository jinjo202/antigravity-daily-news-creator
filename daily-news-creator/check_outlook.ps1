try {
    Write-Host "Creating Outlook COM object..."
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace("MAPI")
    $inbox = $namespace.GetDefaultFolder(6) # 6 = OlFolderInbox
    
    Write-Host "Searching for emails containing '아시아' received today..."
    $today = (Get-Date).Date
    $emails = $inbox.Items | Where-Object { $_.Subject -like "*아시아*" -and $_.ReceivedTime -ge $today }
    
    # Check count
    $count = 0
    foreach ($email in $emails) {
        $count++
        Write-Host "Subject: $($email.Subject)"
        Write-Host "Received: $($email.ReceivedTime)"
        Write-Host "Body Preview (first 500 chars):"
        if ($email.Body.Length -gt 500) {
            Write-Host $email.Body.Substring(0, 500)
        } else {
            Write-Host $email.Body
        }
        Write-Host "----------------------------------------"
        
        # Save email body to a file in workspace
        $outPath = "C:\Users\infomax\OneDrive\dev\Daily news reporter creator\today_report.txt"
        $email.Body | Out-File -FilePath $outPath -Encoding utf8
        Write-Host "Saved email body to $outPath"
    }
    Write-Host "Found and processed $count emails."
} catch {
    Write-Error $_.Exception.Message
}
