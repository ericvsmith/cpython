#ifndef Py_INTERNAL_TOKENIZER_H
#define Py_INTERNAL_TOKENIZER_H
#ifdef __cplusplus
extern "C" {
#endif

extern struct tok_state *_PyTokenizer_FromString(const char *str, int
                                                 exec_input, int lineno,
                                                 int colno);

#ifdef __cplusplus
}
#endif
#endif /* !Py_INTERNAL_TOKENIZER_H */
