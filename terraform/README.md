# terraform

Holder GitHub-oppsettet for dette repoet i kode: squash-only, ingen push rett til
main, grønn CI før merge, og ingen force push eller sletting av main.

```
export GITHUB_TOKEN=$(gh auth token --hostname github.com)
terraform -chdir=terraform init
terraform -chdir=terraform plan
terraform -chdir=terraform apply
```

Repoet finnes allerede, så `main.tf` har en `import`-blokk som adopterer det ved
første `apply`. Den kan fjernes etterpå.

`terraform.tfstate` ligger lokalt og er utenfor git. Sletter du den, adopterer
`import`-blokken repoet på nytt.

Releases lages av release-please: den samler Conventional Commits på main i en
release-PR, og når du merger den, settes taggen og GitHub-releasen. `publish.yml`
bygger og laster opp til PyPI når releasen publiseres.
