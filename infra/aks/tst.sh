for region in northeurope uksouth germanywestcentral swedencentral norwayeast francecentral; do
  echo -n "$region: "
  az aks create \
    --resource-group cnp-rg \
    --name cnp-test-$region \
    --node-count 1 \
    --node-vm-size Standard_B2s \
    --location $region \
    --generate-ssh-keys \
    --no-wait 2>&1 | grep -E "403|Forbidden|Creating|error" | head -1
done
