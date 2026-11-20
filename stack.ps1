# Shared by deploy.ps1 and add-students.ps1: where the stack lives and how to call the AWS CLI.
# Dot-source it; it defines variables and functions only.

$Region = 'ap-south-1'
$StackName = 'indian-painting-gateway'
$KeyNamePrefix = 'indian-painting/'

function Invoke-Aws {
    # Runs the AWS CLI in $Region and throws when it fails. Error output is left on the
    # console rather than redirected, because Windows PowerShell turns redirected native
    # error output into terminating errors.
    $ErrorActionPreference = 'Continue'
    $output = & aws @args --region $Region
    if ($LASTEXITCODE -ne 0) { throw "aws $($args -join ' ') failed with exit code $LASTEXITCODE" }
    $output
}

function Get-StackOutputs {
    $pairs = Invoke-Aws cloudformation describe-stacks --stack-name $StackName --query 'Stacks[0].Outputs' --output json | Out-String | ConvertFrom-Json
    $outputs = @{}
    foreach ($pair in $pairs) { $outputs[$pair.OutputKey] = $pair.OutputValue }
    $outputs
}
