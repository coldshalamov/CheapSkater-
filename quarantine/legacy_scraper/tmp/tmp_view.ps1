$lines = Get-Content logs/app.log
$start= [array]::FindIndex($lines, {$_ -like "*Store selector failed*"}) - 10
if($start -lt 0){$start=0}
$end=$start+40
for($i=$start; $i -lt $end -and $i -lt $lines.Length; $i++){
  Write-Output ("{0}:{1}" -f ($i+1), $lines[$i])
}
