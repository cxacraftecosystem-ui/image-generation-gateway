<#
.SYNOPSIS
Package the Lambda and create or update the gateway stack, then print the API URL.

.EXAMPLE
./deploy.ps1
./deploy.ps1 -ImagesPerDay 600
#>
param(
    [int]$ImagesPerDay = 1000
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\stack.ps1"

function Get-SourceHash([string]$Folder) {
    $hashes = Get-ChildItem $Folder -File | Sort-Object Name | ForEach-Object { "$($_.Name)=$((Get-FileHash $_.FullName).Hash)" }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($hashes -join "`n"))
    -join ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') })
}

function New-LambdaPackage([string]$Folder, [string]$ZipPath) {
    # Entries are named with forward slashes by hand: Lambda runs on Linux, and some
    # Windows zip tools write backslashes that break `import gateway`.
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    if (Test-Path $ZipPath) { Remove-Item $ZipPath }
    $archive = [IO.Compression.ZipFile]::Open($ZipPath, 'Create')
    try {
        $package = Split-Path $Folder -Leaf
        Get-ChildItem $Folder -File | Where-Object Extension -in '.py', '.json' | ForEach-Object {
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, "$package/$($_.Name)")
        }
    } finally {
        $archive.Dispose()
    }
}

$styles = Join-Path $PSScriptRoot 'gateway\styles.json'
if (-not (Test-Path $styles)) {
    throw "gateway\styles.json is missing. Copy styles.example.json there and fill in each LoRA's download address (it is kept out of git)."
}

$account = Invoke-Aws sts get-caller-identity --query Account --output text
$bucket = "$StackName-artifacts-$account"
$existing = Invoke-Aws s3api list-buckets --query "Buckets[?Name=='$bucket'].Name" --output text
if (-not $existing) {
    Write-Host "Creating bucket $bucket"
    Invoke-Aws s3api create-bucket --bucket $bucket --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
}

$source = Join-Path $PSScriptRoot 'gateway'
$codeKey = "lambda/$(Get-SourceHash $source).zip"
$zip = Join-Path ([IO.Path]::GetTempPath()) "$StackName.zip"
New-LambdaPackage $source $zip
Invoke-Aws s3 cp $zip "s3://$bucket/$codeKey" --only-show-errors
Remove-Item $zip

Write-Host "Deploying stack $StackName"
Invoke-Aws cloudformation deploy `
    --stack-name $StackName `
    --template-file (Join-Path $PSScriptRoot 'template.yaml') `
    --capabilities CAPABILITY_IAM `
    --no-fail-on-empty-changeset `
    --tags project=$StackName `
    --parameter-overrides "CodeBucket=$bucket" "CodeKey=$codeKey" "ImagesPerDay=$ImagesPerDay"

# CloudFormation only deploys the API stage when the stack is first created; this
# publishes later changes to routes and error responses too.
$outputs = Get-StackOutputs
Invoke-Aws apigateway create-deployment --rest-api-id $outputs.ApiId --stage-name $outputs.StageName --description "deploy.ps1 $codeKey" | Out-Null
Write-Host "API: $($outputs.ApiUrl)"
