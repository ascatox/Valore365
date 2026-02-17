param(
  [string]$DbUrl = 'postgresql://postgres:postgres@localhost:5432/valore365'
)

Write-Host 'Applying schema...'
psql $DbUrl -f database/schema.sql

Write-Host 'Applying seed...'
psql $DbUrl -f database/seed.sql

if (Test-Path database/migrations) {
  Get-ChildItem database/migrations -Filter *.sql | Sort-Object Name | ForEach-Object {
    Write-Host \"Applying migration $($_.Name)...\"
    psql $DbUrl -f $_.FullName
  }
}

Write-Host 'Database bootstrap completed.'
