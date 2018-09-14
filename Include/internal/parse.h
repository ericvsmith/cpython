#ifndef Py_INTERNAL_PARSE_H
#define Py_INTERNAL_PARSE_H
#ifdef __cplusplus
extern "C" {
#endif

#include "grammar.h"
#include "parsetok.h"

node *
_PyParser_ParseStringObjectEx(const char *s, PyObject *filename,
                              grammar *g, int start,
                              perrdetail *err_ret, int *flags,
                              int lineno, int offset);

#ifdef __cplusplus
}
#endif
#endif /* !Py_INTERNAL_PARSE_H */
