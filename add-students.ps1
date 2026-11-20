<#
.SYNOPSIS
Give each named student their own API key on the gateway and print the keys.
Running it again for a name that already has a key prints that key instead of making another.

.EXAMPLE
./add-students.ps1 "Asha Rao", "Vikram Singh"
./add-students.ps1 (Get-Content students.txt) | Export-Csv student-keys.csv -NoTypeInformation
#>
param(
    [Parameter(Mandatory)][string[]]$Names
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\stack.ps1"

$planId = (Get-StackOutputs).UsagePlanId

foreach ($name in $Names | ForEach-Object { $_.Trim() } | Where-Object { $_ }) {
    $keyName = "$KeyNamePrefix$name"
    $found = Invoke-Aws apigateway get-api-keys --name-query $keyName --include-values --query "items[?name=='$keyName'] | [0].[id,value]" --output text
    if ($found -and $found -ne 'None') {
        $id, $value = $found -split "`t"
    } else {
        $id, $value = (Invoke-Aws apigateway create-api-key --name $keyName --enabled --query '[id,value]' --output text) -split "`t"
        Invoke-Aws apigateway create-usage-plan-key --usage-plan-id $planId --key-id $id --key-type API_KEY | Out-Null
    }
    [pscustomobject]@{ Student = $name; Key = $value }
}
