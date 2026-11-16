/// <reference path="../pb_data/types.d.ts" />

// Historial de conversiones de Mi Cotizador. Cada usuario ve y crea solo
// las suyas; nadie (salvo un superuser) puede editarlas ni borrarlas.
const ES_DUENIO = "usuario = @request.auth.id"

migrate((app) => {
  const users = app.findCollectionByNameOrId("users")

  const consultas = new Collection({
    type: "base",
    name: "consultas",
    fields: [
      {
        type: "relation",
        name: "usuario",
        collectionId: users.id,
        maxSelect: 1,
        required: true,
        // Si se borra la cuenta, se borra su historial.
        cascadeDelete: true,
      },
      // monto no es "required" porque PocketBase rechazaría un monto de 0.
      { type: "number", name: "monto", min: 0 },
      { type: "number", name: "cotizacion", required: true, min: 0 },
      { type: "number", name: "resultado", min: 0 },
      { type: "autodate", name: "fecha", onCreate: true, onUpdate: false },
    ],
    indexes: ["CREATE INDEX idx_consultas_usuario_fecha ON consultas (usuario, fecha)"],
    listRule: ES_DUENIO,
    viewRule: ES_DUENIO,
    createRule:
      '@request.auth.collectionName = "users" && @request.auth.desactivado = false && @request.body.usuario = @request.auth.id',
    updateRule: null,
    deleteRule: null,
  })

  app.save(consultas)
}, (app) => {
  app.delete(app.findCollectionByNameOrId("consultas"))
})
