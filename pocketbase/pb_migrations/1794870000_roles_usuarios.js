/// <reference path="../pb_data/types.d.ts" />

// Agrega rol y desactivación a los usuarios, y deja que solo un admin
// pueda ver todas las cuentas, desactivarlas y cambiar su contraseña.
const ES_ADMIN = '@request.auth.rol = "admin"'

migrate((app) => {
  const users = app.findCollectionByNameOrId("users")

  users.fields.add(new SelectField({
    name: "rol",
    values: ["usuario", "admin"],
    maxSelect: 1,
  }))
  users.fields.add(new BoolField({ name: "desactivado" }))

  // Cada uno ve su propia cuenta; el admin ve todas.
  users.listRule = `id = @request.auth.id || ${ES_ADMIN}`
  users.viewRule = `id = @request.auth.id || ${ES_ADMIN}`
  // Al registrarse nadie puede darse rol ni desactivar la cuenta.
  users.createRule = "@request.body.rol:isset = false && @request.body.desactivado:isset = false"
  // Cada uno edita sus datos pero no su rol ni su estado; el admin edita cualquiera.
  users.updateRule =
    `(id = @request.auth.id && @request.body.rol:isset = false && @request.body.desactivado:isset = false) || ${ES_ADMIN}`
  // Permite al admin cambiar la contraseña de otros sin conocer la anterior.
  users.manageRule = ES_ADMIN
  // Las cuentas desactivadas no pueden iniciar sesión.
  users.authRule = "desactivado = false"

  app.save(users)
}, (app) => {
  const users = app.findCollectionByNameOrId("users")

  users.fields.removeByName("rol")
  users.fields.removeByName("desactivado")
  users.listRule = "id = @request.auth.id"
  users.viewRule = "id = @request.auth.id"
  users.createRule = ""
  users.updateRule = "id = @request.auth.id"
  users.manageRule = null
  users.authRule = ""

  app.save(users)
})
